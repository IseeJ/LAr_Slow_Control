import time

import Doberman
import collections

__all__ = 'PipelineMonitor'.split()


class PipelineMonitor(Doberman.Monitor):
    """
    A subclass to handle a pipeline or pipelines. Pipelines come in three main flavors: they either process or send alarms,
    convert "raw" values into "processed" values, or control something in the system. Each flavor is handled by one
    dedicated PipelineMonitor.
    """

    def setup(self):
        self.listeners = collections.defaultdict(dict)
        self.pipelines = {}
        flavor = self.name.split('_')[1]  # pl_flavor
        if flavor not in 'alarm control convert'.split():
            raise ValueError(
                f'Unknown pipeline monitor {self.name}, allowed are "pl_alarm", "pl_convert", "pl_control"')
        for name in self.db.get_pipelines(flavor):
            self.start_pipeline(name)
        if self.name == 'pl_control':
            # hard-code the test routine. It runs through one cycle then stops itself
            self.start_pipeline('test_pipeline')

    def shutdown(self):
        self.logger.info(f'{self.name} shutting down')
        for p in list(self.pipelines.keys()):
            self.stop_pipeline(p, keep_status=True)

    def start_pipeline(self, name):
        if (doc := self.db.get_pipeline(name)) is None:
            self.logger.error(f'No pipeline named {name} found')
            return
        if name in self.pipelines:
            self.logger.error(f'I already manage a pipeline called {name}')
            return
        self.logger.info(f'Starting pipeline {name}')
        self.db.set_pipeline_value(name, [('status', 'active')])
        self.db.set_pipeline_value(name, [('silent_until', 0)])
        try:
            p = Doberman.Pipeline.create(doc, db=self.db,
                                         logger=Doberman.utils.get_child_logger(name, self.db, self.logger),
                                         name=name, monitor=self)
            p.build(doc)
        except Exception as e:
            self.logger.error(f'{type(e)}: {e}')
            self.db.set_pipeline_value(name, [('status', 'inactive')])
            self.logger.error(f'Could not build pipeline {name}')
            return
        self.register(obj=p, name=name)
        self.pipelines[p.name] = p
        return 0

    def stop_pipeline(self, name, keep_status=False):
        self.logger.info(f'stopping pipeline {name}')
        self.pipelines[name].stop(keep_status=keep_status)
        self.stop_thread(name)
        del self.pipelines[name]

    def testalarm(self, level):
        message = f"This is a level {level} test alarm"
        try:
            self.log_alarm(level, message)
        except Exception as e:
            self.logger.error(f"Got a {type(e)} while sending level {level} alarm: {e}")

    def process_command(self, command):
        try:
            if command.startswith('pipelinectl_start'):
                _, name = command.split(' ')
                self.start_pipeline(name)
            elif command.startswith('pipelinectl_stop'):
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.stop_pipeline(name)
            elif command.startswith('pipelinectl_restart'):
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.stop_pipeline(name)
                    self.start_pipeline(name)
            elif command.startswith('pipelinectl_silent'):
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.logger.info(f'Silencing {name}')
                    self.db.set_pipeline_value(name, [('silent_until', -1)])
            elif command.startswith('pipelinectl_active'):
                _, name = command.split(' ')
                if name not in self.pipelines:
                    self.logger.error(f'I don\'t control the "{name}" pipeline')
                else:
                    self.logger.info(f'Activating {name}')
                    self.db.set_pipeline_value(name, [('silent_until', time.time())])
            elif command == 'stop':
                self.sh.event.set()
            elif command.startswith('testalarm'):
                _, level = command.split(' ')
                self.logger.info(f'Sending level {level} test alarm')
                self.testalarm(int(level))
            else:
                self.logger.error(f'I don\'t understand command "{command}"')
        except Exception as e:
            self.logger.error(f'Got a {type(e)} while processing command "{command}": {e}')
