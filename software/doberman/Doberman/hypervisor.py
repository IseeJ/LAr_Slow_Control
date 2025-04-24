import Doberman
import subprocess
import time
import os
import threading
import json
import datetime
import zmq
from heapq import heappush, heappop

dtnow = Doberman.utils.dtnow


class Hypervisor(Doberman.Monitor):
    """
    A tool to monitor and restart processes when necessary. It is assumed
    that this is the first thing started, and that nothing is already running.
    """

    def setup(self) -> None:
        print("Hypervisor.setup()")
        self.logger.info(f'HYPERVISOR SETUP()')
        self.update_config(status='online')
        self.debug_flag = ' --debug' if self.debug else ''
        self.config = self.db.get_experiment_config('hypervisor')
        self.localhost = self.config['host']
        print(f"self.localhost = {self.localhost}")
        self.username = self.config.get('username', os.environ['USER'])

        # do any startup sequences
        for host, activities in self.config.get('startup_sequence', {}).items():
            print(f"host, activities = {host}, {activities}")
            if host == self.localhost:
                for activity in activities:
                    self.run_locally(activity)
            else:
                for activity in activities:
                    self.run_over_ssh(f'{self.username}@{host}', activity)

        self.last_pong = {}
        # start the three Pipeline monitors
        path = self.config['path']
        for thing in 'alarm control convert'.split():
            self.run_locally(f'cd {path} && ./start_process.sh --{thing}{self.debug_flag}')
            self.last_pong[f'pl_{thing}'] = time.time()
            time.sleep(0.1)
        # now start the rest of the things
        self.known_devices = self.db.distinct('devices', 'name')
        self.cv = threading.Condition()
        self.dispatcher = threading.Thread(target=self.dispatch)
        self.dispatcher.start()  # TODO get this registered somehow
        self.broker_context = zmq.Context.instance()
        self.broker = threading.Thread(target=self.data_broker, args=(self.broker_context,))
        self.broker.start()
        self.register(obj=self.compress_logs, period=86400, name='log_compactor', _no_stop=True)
        rhbs = self.config.get('remote_heartbeat', [])
        print(rhbs)
        for rhb in rhbs:
            self.register(obj=self.send_remote_heartbeat, period=60, name='remote_heartbeat', _no_stop=True, config=rhb)
        time.sleep(1)

        # start the fixed-frequency sync signals
        self.db.delete_documents('sensors', {'name': {'$regex': '^X_SYNC'}})
        periods = self.config.get('sync_periods', [5, 10, 15, 30, 60])
        for i in periods:
            if self.db.get_sensor_setting(name=f'X_SYNC_{i}') is None:
                self.db.insert_into_db('sensors',
                                       {'name': f'X_SYNC_{i}', 'description': 'Sync signal', 'readout_interval': i,
                                        'status': 'offline', 'topic': 'other',
                                        'subsystem': 'sync', 'pipelines': [], 'device': 'hypervisor', 'units': '',
                                        'readout_command': ''})
        self.sync = threading.Thread(target=self.sync_signals, args=(periods,))
        self.sync.start()

        time.sleep(1)
        self.register(obj=self.hypervise, period=self.config['period'], name='hypervise', _no_stop=True)

    def shutdown(self) -> None:
        for thing in 'alarm control convert'.split():
            self.run_locally(f"screen -S pl_{thing} -X quit")
            self.update_config(deactivate=f'pl_{thing}')
            time.sleep(0.1)
        managed = self.config['processes']['managed']
        for device in managed:
            self.stop_device(device)
            time.sleep(0.05)
        self.update_config(status='offline')
        self.dispatcher.join(timeout=5)
        self.broker_context.term()
        self.broker.join(timeout=5)
        self.sync.join(timeout=5)

    def sync_signals(self, periods: list) -> None:
        ctx = zmq.Context.instance()
        socket = ctx.socket(zmq.PUB)
        host, ports = self.db.get_comms_info('data')
        socket.connect(f'tcp://{host}:{ports["send"]}')
        now = time.time()
        q = [(now + p, p) for p in sorted(periods)]
        while not self.event.is_set():
            self.event.wait(q[0][0] - time.time())
            _, p = heappop(q)
            now = time.time()
            socket.send_string(f'X_SYNC_{p} {now:.3f} 0')
            heappush(q, (now + p, p))

    def update_config(self, unmanage=None, manage=None, activate=None, deactivate=None, heartbeat=None,
                      status=None) -> None:
        updates = {}
        if unmanage:
            updates['$pull'] = {'processes.managed': unmanage}
        if manage:
            updates['$addToSet'] = {'processes.managed': manage}
        if activate:
            updates['$addToSet'] = {'processes.active': activate}
        if deactivate:
            updates['$pull'] = {'processes.active': deactivate}
        if heartbeat:
            updates['$set'] = {'heartbeat': heartbeat}
        if status:
            updates['$set'] = {'status': status}
        if updates:
            self.db.update_db('experiment_config', {'name': 'hypervisor'}, updates)

    def hypervise(self) -> None:
        while not self.event.is_set():
            self.logger.debug('Hypervising')
            self.config = self.db.get_experiment_config('hypervisor')
            managed = self.config['processes']['managed']
            active = self.config['processes']['active']
            self.known_devices = self.db.distinct('devices', 'name')
            path = self.config['path']
            for pl in 'alarm control convert'.split():
                if time.time() - self.last_pong.get(f'pl_{pl}', 100) > 30:
                    self.logger.warning(f'Failed to ping pl_{pl}, restarting it')
                    self.run_locally(f'cd {path} && ./start_process.sh --{pl}{self.debug_flag}')
            for device in managed:
                if device not in active:
                    # device isn't running and it's supposed to be
                    self.logger.info(f'{device} is managed but not active. I will start it.')
                    if self.start_device(device):
                        # nonzero return code, probably something didn't work
                        self.logger.error(f'Problem starting {device}, check the logs')
                elif (dt := (dtnow() - self.db.get_heartbeat(device=device)).total_seconds()) > 2 * \
                        self.config['period']:
                    # device claims to be active but hasn't heartbeated recently
                    self.logger.error(f'{device} had no heartbeat for {int(dt)} seconds, it\'s getting restarted')
                    if self.start_device(device):
                        # nonzero return code, probably something didn't work
                        self.logger.error(f'Problem starting {device}, check the logs')
                    else:
                        self.logger.info(f'{device} restarted')
                elif time.time() - self.last_pong.get(device, 100) > 30:
                    self.logger.error(f'Failed to ping {device}, restarting it')
                    self.start_device(device)
                else:
                    # claims to be active and has heartbeated recently
                    self.logger.debug(f'{device} last heartbeat {int(dt)} seconds ago')
                time.sleep(0.1)
            self.update_config(heartbeat=dtnow())
            return self.config['period']

    def send_remote_heartbeat(self, config) -> None:
        print("hypervisor.send_remote_heartbeat()")
        # touch a file on a remote server just so someone else knows we're still alive
        numbers = ','.join(doc['sms'] for doc in self.db.read_from_db('contacts', {'on_shift': True}))
        if (addr := config.get('address')) is not None:
            directory = config.get('directory', '/scratch')
            self.run_over_ssh(addr,
                              f"date +%s > {directory}/remote_hb_{self.db.experiment_name}",
                              port=config.get('port', 22))
            self.run_over_ssh(addr,
                              f'echo "{numbers}" >> {directory}/remote_hb_{self.db.experiment_name}',
                              port=config.get('port', 22))

    def run_over_ssh(self, address: str, command: str, port=22) -> int:
        """
        Runs a command over ssh, stdout/err will go to the debug logs
        :param address: user@host
        :param command: the command to run. Will be wrapped in double-quotes, a la ssh user@host "command"
        :param port: the port you use for ssh connections if it isn't the default 22
        :returns: return code of ssh
        """
        print(f"hypervisor.run_over_ssh(): {address}, {command}, {port}")
        cmd = ['ssh', address, f'"{command}"']
        print(f'  cmd = [{cmd}]')
        if port != 22:
            cmd.insert(1, '-p')
            cmd.insert(2, f'{port}')
        self.logger.debug(f'Running "{" ".join(cmd)}"')
        try:
            cp = subprocess.run(' '.join(cmd), shell=True, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            self.logger.error(f'Command to {address} timed out!')
            return -1
        if cp.stdout:
            self.logger.debug(f'Stdout: {cp.stdout.decode()}')
        if cp.stderr:
            self.logger.error(f'Stderr: {cp.stderr.decode()}')
        time.sleep(1)
        return cp.returncode

    def run_locally(self, command: str) -> int:
        """
        Some commands don't want to run via ssh?
        """
        print(f"hypervisor.run_locally(): {command}")
        cp = subprocess.run(command, shell=True, capture_output=True)
        if cp.stdout:
            self.logger.debug(f'Stdout: {cp.stdout.decode()}')
        if cp.stderr:
            self.logger.error(f'Stderr: {cp.stderr.decode()}')
        time.sleep(1)
        return cp.returncode

    def start_device(self, device: str) -> int:
        print("hypervisor.start_device()")
        path = self.config['path']
        doc = self.db.get_device_setting(device)
        host = doc['host']
        self.update_config(manage=device)
        command = f"cd {path} && ./start_process.sh -d {device}{self.debug_flag}"
        if host == self.localhost:
            return self.run_locally(command)
        return self.run_over_ssh(f'{self.username}@{host}', command)

    def stop_device(self, device: str) -> int:
        doc = self.db.get_device_setting(device)
        host = doc['host']
        self.update_config(deactivate=device)
        command = f"screen -S {device} -X quit"
        if host == self.localhost:
            return self.run_locally(command)
        return self.run_over_ssh(f'{self.username}@{host}', command)

    def compress_logs(self) -> None:
        then = dtnow() - datetime.timedelta(days=7)
        self.logger.info(f'Compressing logs from {then.year}-{then.month:02d}-{then.day:02d}')
        p = self.logger.handlers[0].oh.get_logdir(dtnow() - datetime.timedelta(days=7))
        self.run_locally(f'cd {p} && gzip --best *.log')

    def data_broker(self, ctx) -> None:
        """
        This functions sets up the middle-man for the data-passing subsystem
        """
        incoming = ctx.socket(zmq.XSUB)
        outgoing = ctx.socket(zmq.XPUB)

        _, ports = self.db.get_comms_info('data')

        # ports seem backwards because they should be here and only here
        incoming.bind(f'tcp://*:{ports["send"]}')
        outgoing.bind(f'tcp://*:{ports["recv"]}')

        try:
            zmq.proxy(incoming, outgoing)
        except zmq.ContextTerminated:
            incoming.close()
            outgoing.close()

    def dispatch(self, ping_period=5) -> None:
        """
        Handles the command-passing communication subsystem.

        :param ping_period: Frequency of ping messages in seconds. Default is 5 seconds.
        """
        ctx = zmq.Context.instance()

        with ctx.socket(zmq.REP) as incoming, ctx.socket(zmq.PUB) as outgoing:
            _, ports = self.db.get_comms_info('command')

            incoming.bind(f'tcp://*:{ports["send"]}')
            outgoing.bind(f'tcp://*:{ports["recv"]}')

            poller = zmq.Poller()
            poller.register(incoming, zmq.POLLIN)

            last_ping = time.time()
            queue = []
            cmd_ack = {}

            while not self.event.is_set():
                timeout_ms = self.calculate_timeout_ms(queue, last_ping, ping_period)
                socks = dict(poller.poll(timeout=int(timeout_ms)))

                if (now := time.time()) - last_ping > ping_period or not len(socks):
                    outgoing.send_string("ping ")
                    last_ping = now

                if socks.get(incoming) == zmq.POLLIN:
                    self.handle_incoming_message(incoming, queue, cmd_ack, now)

                if self.is_time_for_next_command(queue, now):
                    self.process_next_command(queue, outgoing, cmd_ack, now)

                self.remove_stale_acknowledgements(cmd_ack)

    def calculate_timeout_ms(self, queue, last_ping, ping_period):
        next_ping = last_ping + ping_period - time.time()
        next_command = queue[0][0] - time.time() if queue else ping_period
        return min(next_ping, next_command) * 1000

    def handle_incoming_message(self, incoming, queue, cmd_ack, now):
        msg = incoming.recv_string()
        incoming.send_string("")  # Must reply

        if msg.startswith('pong'):
            _, name = msg.split(' ')
            self.last_pong[name] = now
        elif msg.startswith('{'):
            self.process_external_command(msg, queue)
        elif msg.startswith('ack'):
            self.process_acknowledgement(msg, cmd_ack)
        else:
            self.process_command(msg)

    def process_external_command(self, msg, queue):
        try:
            doc = json.loads(msg)
            heappush(queue, (float(doc['time']), doc['to'], doc['command']))
        except Exception as e:
            self.logger.error(f'Error processing "{msg}": {e}')

    def process_acknowledgement(self, msg, cmd_ack):
        try:
            _, name, cmd_hash = msg.split(' ')
            del cmd_ack[cmd_hash]
        except KeyError:
            self.logger.error(f'Unknown hash: {msg}')
        except Exception as e:
            self.logger.error(f'Error processing "{msg}": {e}')

    def is_time_for_next_command(self, queue, now):
        return len(queue) > 0 and queue[0][0] - now < 0.001

    def process_next_command(self, queue, outgoing, cmd_ack, now):
        _, to, cmd = heappop(queue)
        if to == 'hypervisor':
            self.process_command(cmd)
        else:
            cmd_hash = Doberman.utils.make_hash(now, to, cmd, hash_length=6)
            outgoing.send_string(f'{to} {cmd_hash} {cmd}')
            cmd_ack[cmd_hash] = (to, dtnow())

    def remove_stale_acknowledgements(self, cmd_ack):
        keys_to_pop = []
        for key, (name, timestamp) in cmd_ack.items():
            if (dtnow() - timestamp).total_seconds() > 5:
                self.logger.error(f"Command to {name} hasn't been ack'd in over 5 seconds")
                keys_to_pop.append(key)
        for key in keys_to_pop:
            cmd_ack.pop(key, None)

    def process_command(self, command: str) -> None:
        self.logger.info(f'Processing {command}')
        if command.startswith('start'):
            _, target = command.split(' ', maxsplit=1)
            self.logger.info(f'Hypervisor starting {target}')
            if target in self.known_devices:
                self.start_device(target)
            else:
                self.logger.error(f'Don\'t know what "{target}" is, can\'t start it')

        elif command.startswith('manage'):
            _, device = command.split(' ', maxsplit=1)
            if device not in self.known_devices:
                # unlikely but you can never trust users
                self.logger.error(f'Hypervisor can\'t manage {device}')
                return
            self.logger.info(f'Hypervisor now managing {device}')
            self.update_config(manage=device)

        elif command.startswith('unmanage'):
            _, device = command.split(' ', maxsplit=1)
            if device not in self.known_devices:
                # unlikely but you can never trust users
                self.logger.error(f'Hypervisor can\'t unmanage {device}')
                return
            self.logger.info(f'Hypervisor relinquishing control of {device}')
            self.update_config(unmanage=device)

        elif command.startswith('kill'):
            # I'm sure this will be useful at some point
            _, thing = command.split(' ', maxsplit=1)
            if thing in self.known_devices:
                host = self.db.get_device_setting(thing, field='host')
                self.run_over_ssh(host, f"screen -S {thing} -X quit")
            else:
                # assume it's running on localhost?
                self.run_locally(f"screen -S {thing} -X quit")

        else:
            self.logger.error(f'Command "{command}" not understood')
