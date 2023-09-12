import os
import sys
import time
import json
import shlex
import pickle
import inspect
import subprocess
from datetime import datetime
from filelock import FileLock

class Mutex:

    def __init__(self, name):

        '''
        we use file locking because it is system-wide mutex compatible with all operating systems
        it is well suited for synchronizing multiple processes
        '''

        self.lock = FileLock(self.CreatePath(name))

    def CreatePath(self, name):

        '''
        create a .lock file path, locks and other synchronization primitives are stored in folder 'sync'
        we will try to lock this file and use it as a mutex
        '''

        file_name = '%s.lock' % name
        path = os.path.join('sync', file_name)
        return path

    def __enter__(self):

        '''
        lock the file (mutex), only one process can have this file locked at the same time
        others processes will have to wait until it is unlocked
        '''

        self.lock.acquire()

    def __exit__(self, exc_type, exc_value, traceback):

        '''
        unlock the file (release the mutex), now other processes will be able to acquire the lock
        '''

        self.lock.release()

class Value:

    def __init__(self, name, initial_value):

        '''
        persistent atomic value (can be any type), which can be read from the file in case of process crash
        takes 'name' as an argument - name must be unique
        '''

        self.path = self.CreatePath(name)
        self.mutex = Mutex(os.path.split(self.path)[-1])
        self.initial_value = initial_value

    def CreatePath(self, name):

        '''
        create a file path of the .value file, like other synchronization primitives it is stored in folder 'sync'
        '''

        file_name = '%s.value' % name
        path = os.path.join('sync', file_name)
        return path

    def Get(self):

        '''
        get the value, value is read from the file, if .value file is not yet created returns initial value
        '''

        with self.mutex:
            if os.path.isfile(self.path):
                with open(self.path, 'rb') as file:
                    value = pickle.load(file)
            else:
                value = self.initial_value

        return value

    def Set(self, value):

        '''
        set the new value, overwrite the old value in .value file
        '''

        with self.mutex:
            with open(self.path, 'wb') as file:
                pickle.dump(value, file)

    def __enter__(self):

        '''
        acquire the mutex in case we want to several operations to be atomic, 
        for example: get value, increase it and then set it
        '''

        self.mutex.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):

        '''
        release the mutex
        '''

        self.mutex.__exit__(exc_type, exc_value, traceback)

class StdOut:

    def __init__(self):

        '''
        class for overloading stdout and stderr, we need it to because we will also log print statements 
        and exceptions to the file, if long running process crashes, we will later be able to check the reason for crash
        '''

        self.stdout = sys.stdout
        self.mutex = Mutex('stdout')
        self.path = os.path.join('logs', 'stdout.log')
        self.pid = os.getpid()

    def write(self, text):

        '''
        function which overloads sys.stdout.write and sys.stderr.write
        we use mutex that different processes would not overwrite each other logs
        '''

        if text == '\n':
            return

        time_now = datetime.now().replace(microsecond=0)
        text = '[%s][Process %d] %s\n' % (time_now, self.pid, text)

        self.stdout.write(text)
        with self.mutex:
            with open(self.path, 'a') as file:
                file.write(text)

    def flush(self):

        '''
        function which overloads sys.stdout.flush and sys.stderr.flush
        '''

        self.stdout.flush()

    def redirect(self):

        '''
        redirect both stdout and stderr to the instance of this class
        now everything will be printed to console as well as written to file in folder 'logs'
        '''

        sys.stdout = sys.stderr = self

class Pool:

    def __init__(self, count=None):

        '''
        process pool for parallel execution of particular functions, takes process count as an argument
        if count is not specified then we spawn as much processes as processor has cores
        '''
        
        self.count = count or os.cpu_count()

    def CreateCommand(self, func, args):

        '''
        to run function in other process, we create a command line statement to call python and execute particular code
        the code is required to import function or class from its module, and execute the function
        '''

        module = inspect.getmodule(func)
        module_name = os.path.basename(module.__file__).replace('.py', '')

        segments = func.__qualname__.split('.')
        if len(segments) == 1:
            class_name, func_name = None, segments[0]
        elif len(segments) == 2:
            class_name, func_name = segments
        else:
            raise NotImplementedError
        
        args = ','.join(json.dumps(arg).replace('"', '\'') for arg in args)
        python = 'python' if sys.platform == 'win32' else 'python3'
        if class_name is None:
            code = 'from %s import %s; %s(%s)' % (module_name, func_name, func_name, args)
        else:
            code = 'from %s import %s; %s(%s).%s()' % (module_name, class_name, class_name, args, func_name)
        command = '%s -c "import os; os.environ.setdefault(\'child_process\', \'1\'); %s"' % (python, code)

        return command

    def Run(self, func, *args):

        '''
        create all processes and assign a particular function for them to execute
        we will be constantly checking if all of them are still alive, if all of them finished successfully 
        we break the loop, if one of them crashed, we terminate the other processes and also break the loop
        '''

        processes = []
        command = shlex.split(self.CreateCommand(func, args))
        for iteration in range(self.count):
            process = subprocess.Popen(command)
            processes.append(process)

        while 1:
            time.sleep(1)
            finished_processes, crashed_processes = 0, 0

            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    if return_code == 0:
                        finished_processes += 1
                    else:
                        crashed_processes += 1

            if finished_processes == len(processes) or crashed_processes > 0:
                for process in processes:
                    process.kill()
                    process.wait()
                break

    @staticmethod
    def IsMainProcess():

        '''
        distinguish between main and child processes as we dont want childs to run main process functions
        when we spawn child processes in 'Run' function we also set environment variable 'child_process'
        this helps us to avoid infinite recursion when every subsequent child process spawn its own pool of child processes
        '''
        
        return 'child_process' not in os.environ