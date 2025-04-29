#from pymongo import MongoClient
import pymongo
import os

c = pymongo.MongoClient(os.environ['DOBERMAN_MONGO_URI'])
experiment = os.environ['DOBERMAN_EXPERIMENT_NAME']

db = c[experiment]

####################################
######## DEVICES
db.devices.delete_many({}) # remove all contents
db.devices.create_index({'name': pymongo.ASCENDING})
db.devices.insert_many([
    {
        "name" : "RevPi1",
        #"host" : "revpi-core.wellesley.edu", 
        "host" : "revpi-core",
        "sensors" : [
            "PM_ANODE_HV_Vmon"     # analog signals via AIO
            #"PM_ANODE_HV_Imon",
            #"PM_ANODEMESH_HV_Vmon",
            #"PM_ANODEMESH_HV_Imon"
        ],
    },
    {
        "name" : "OmegaDPI8",
        "address" : {
            "ip" : "10.143.0.42",  # can this be a name or must it be x.x.x.x?
            "port" : 1000
        },
        "host" : "johnson.wellesley.edu",
        "sensors" : [
            "Pressure_Transducer"     # in cryostat
        ],
    },
    {
        "name" : "Waveshare485",
        "address" : {
            "ip" : "10.143.0.46",  # can this be a name or must it be x.x.x.x?
            "port" : 4196
        },
        "host" : "johnson.wellesley.edu",
        "sensors" : [
            "Hornet_IonGauge",     # in cryostat
            "Hornet_ConvectionGauge"
        ],
    },
    #IJ added 01/24/25 for humidity sensor
    {
        "name" : "Waveshare4",
        "address" : {
            "ip" : "10.143.0.48",  
            "port" : 4196  
        },
        "host" : "johnson.wellesley.edu",
        "sensors" : [
            "Humidity_Sensor1",
            "Humidity_Sensor2",
            "Humidity_Sensor3"
        ],
    },
    #newline added by Sunshine 3/31/25, for SR630
    {
        "name" : "Waveshare5",
        "address" : {
            "ip" : "10.143.0.54",  
            "port" : 4196  
        },
        "host" : "johnson.wellesley.edu",
        "sensors" : [
            "temp1",
            "temp2",
            "temp3"
        ],
    },
    {
        "name" : "Waveshare3",
        "address" : {
            "ip" : "10.143.0.47",
            "port" : 4196
        },
        "host" : "johnson.wellesley.edu",
        "sensors" : [
            "Pressure_Sensor",
        ],
    }
    ])

####################################
######## SENSORS
db.sensors.delete_many({}) # remove all contents
db.sensors.create_index({'name': pymongo.ASCENDING})
db.sensors.insert_many([
    {
        "name" : "PM_ANODE_HV_Vmon",
        "description" : "Voltage monitor for Anode of purity monitor",
        "units" : "V",  # actual reading is 1V/1kV, but will convert to kV
        "status" : "online",
        "topic" : "voltages",
        "subsystem" : "purity_monitor",
        "readout_interval" : 3,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [1, 4000], # in volts
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "RevPi1",
        "value_xform" : [0,1000], # convert 1V to 1kV
        "readout_command" : "r AnalogInput_1" # ??? for MIO reading in RevolutionPi
    },
    {
        "name" : "Pressure_Transducer",
        "description" : "Absolute pressure in cryostat",
        "units" : "psi",
        "status" : "online",
        "topic" : "pressures",
        "subsystem" : "cryostat",
        "readout_interval" : 2,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000], # in volts
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "OmegaDPI8",
        "value_xform" : [0,1], # no scaling
        "readout_command" : '01X01' # request a reading from OmegaDPI8
    },
    {
        "name" : "Hornet_IonGauge",
        "description" : "Ionization gauge in cryostat",
        "units" : "torr",
        "status" : "online",
        "topic" : "pressures",
        "subsystem" : "cryostat",
        "readout_interval" : 2,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000], # in volts
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare485",
        "value_xform" : [0,1], # no scaling
        "readout_command" : '01RD' # request a reading from OmegaDPI8
    },
    {
        "name" : "Hornet_ConvectionGauge",
        "description" : "Convection gauge in cryostat",
        "units" : "torr",
        "status" : "online",
        "topic" : "pressures",
        "subsystem" : "cryostat",
        "readout_interval" : 2,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000], # in volts
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare485",
        "value_xform" : [0,1], # no scaling
        "readout_command" : '01RDCG1' # request a reading from OmegaDPI8
    },
    {
        "name" : "Pressure_Sensor",
        "description" : "Pressure reading from EZOPRS for purifier",
        "units" : "atm",
        "status" : "online",
        "topic" : "pressures",
        "subsystem" : "purifier",
        "readout_interval" : 2,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000],
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare3",
        "value_xform" : [0,1], # no scaling
        "readout_command" : 'R', #request one reading
    },
    {
        "name" : "Humidity_Sensor1",
        "description" : "Humidity reading from EZOHUM for purifier",
        "units" : "percent",
        "status" : "online",
        "topic" : "humidity",
        "subsystem" : "purifier",
        "readout_interval" : 2,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000], 
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare4",
        "value_xform" : [0,1], # no scaling
        "readout_command" : 'R', #request one reading
        "multi_sensor": ["Humidity_Sensor1", "Humidity_Sensor2", "Humidity_Sensor3"]
    },
#Humidity sensor, one sensor reads 3 values: HUM, TMP, DEW Some sensor will not read a single quantity but a whole list of quantities (e.g. a levelmeter box with six inputs returns an array of those six values given a single readout_command). This is realised through the MultiSensor class. 
    {
        "name" : "Humidity_Sensor2",
        "description" : "Temperature reading from EZOHUM for purifier",
        "units" : "celsius",
        "status" : "online",
        "topic" : "humidity",
        "subsystem" : "purifier",
        "readout_interval" : 2,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000],
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare4",
        "value_xform" : [0,1], # no scaling
        "readout_command" : 'R', #request one reading
        "multi_sensor": ["Humidity_Sensor1"]
    },
    {
        "name" : "Humidity_Sensor3",
        "description" : "Dew Point reading from EZOHUM for purifier",
        "units" : "celsius",
        "status" : "online",
        "topic" : "humidity",
        "subsystem" : "purifier",
        "readout_interval" : 2,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000],
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare4",
        "value_xform" : [0,1], # no scaling
        "readout_command" : 'R', #request one reading                                                            
        "multi_sensor": ["Humidity_Sensor1"]
    },
    {
        "name" : "temp1",
        "description" : "Temp sensor1 for purifier",
        "units" : "celsius",
        "status" : "online",
        "topic" : "temperature",
        "subsystem" : "purifier",
        "readout_interval" : 10,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000],
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare5",
        "value_xform" : [0,1], # no scaling
        "readout_command" : 'MEAS?6;MEAS?7;MEAS?8;', #request one reading
        "multi_sensor": ["temp1", "temp2", "temp3"]
    },
        {
        "name" : "temp2",
        "description" : "Temp sensor2 for purifier",
        "units" : "celsius",
        "status" : "online",
        "topic" : "temperature",
        "subsystem" : "purifier",
        "readout_interval" : 10,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000],
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare5",
        "value_xform" : [0,1], # no scaling
        "readout_command" : 'MEAS?6;MEAS?7;MEAS?8;', #request one reading
        "multi_sensor": ["temp1"]
        },
    
        {
        "name" : "temp3",
        "description" : "Temp sensor3 for purifier",
        "units" : "celsius",
        "status" : "online",
        "topic" : "temperature",
        "subsystem" : "purifier",
        "readout_interval" : 10,
        "alarm_recurrence" : 3,
        "alarm_thresholds" : [25, 1000],
        "alarm_level" : 0,
        "alarm_is_triggered" : False,
        "pipelines" : [],
        "device" : "Waveshare5",
        "value_xform" : [0,1], # no scaling
        "readout_command" : 'MEAS?6;MEAS?7;MEAS?8;', #request one reading
        "multi_sensor": ["temp1"]
        }
])


####################################
######## HOSTS
db.hosts.delete_many({}) # remove all contents
db.hosts.create_index({'name': pymongo.ASCENDING})
db.hosts.insert_many([
    {"name":"johnson.wellesley.edu", "plugin_dir":["/global/software/doberman_largon"]},
    {"name":"johnson", "plugin_dir":["/global/software/doberman_largon"]},
    {"name":"revpi-core.wellesley.edu", "plugin_dir":["/global/software/doberman_largon"]},
    {"name":"revpi-core", "plugin_dir":["/global/software/doberman_largon"]}
  ])

db.readings.create_index({'name': pymongo.ASCENDING})

db.shifts.create_index({'start': pymongo.ASCENDING, 'end': pymongo.DESCENDING})


db.experiment_config.delete_many({}) # remove all contents of experiment_config
db.experiment_config.insert_many([
    {'name': 'hypervisor', 'processes': {'managed': [], 'active': []}, 'period': 60, 'restart_timeout': 300,
     'status': 'offline', 'path': '/global/software/doberman/scripts',
     #'remote_heartbeat' : [ {'address' : 'doberman@johnson.wellesley.edu', 'port' :22, 'directory': '/global'}, ],
     'host': 'johnson.wellesley.edu', 'username': 'doberman',
     'startup_sequence': {'johnson.wellesley.edu': [],},
                         #calliope: [ '[ -e /global/software ] || mount /global' ],
                         #...},
     'comms': { 'data': {'send': 8904, 'recv': 8905},  'command': {'send': 8906, 'recv': 8907} },
     },
     #
     {'name': 'influx', 'url': 'http://johnson.wellesley.edu:8086/', 'token': 'RPeex4hNPj7n5J8W5mhovr5aDfbbUoGgVeaA8fJ6TemPQQ_QIuHZWK7Gy7rjXiSF03kKBYTz0W_qOBmMnBYgIQ==', 'org': 'largon',
      'precision': 'ms', 'bucket': '2dee3b8039793938', 'db': 'slowcontrol'
      },
     #
     {'name': 'alarms',
      'email': {'contactaddr': '', 'server': '', 'port': 0, 'fromaddr': '', 'password': ''},
      'sms': {'contactaddr': '', 'server': '', 'identification': ''}
     }
])

db.logged_alarms.create_index({'acknowledged': 1})

db.logs.create_index({'level': 1})
db.logs.create_index({'date': 1})
db.logs.create_index({'name': 1})
