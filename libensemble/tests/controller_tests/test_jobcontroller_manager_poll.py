#!/usr/bin/env python

# ********************* NOT YET IMPLEMENTED ***********************
# ********************* Interface demo: see jobctl.manager_poll(job)

# Test of job controller module for libensemble:
#  Detecting manager kill signal
#  This keeps MPI out of user code and is portable across different
#  worker concurrency schemes (MPI/threading/multiprocessing)

# Test does not require running full libensemble

import os
from libensemble.executors.controller import JobController


def build_simfunc():
    import subprocess

    # Build simfunc
    # buildstring='mpif90 -o my_simjob.x my_simjob.f90' # On cray need to use ftn
    buildstring = 'mpicc -o my_simjob.x simdir/my_simjob.c'
    # subprocess.run(buildstring.split(),check=True) # Python3.5+
    subprocess.check_call(buildstring.split())


# --------------- Calling script ------------------------------------------

# sim_app = 'simdir/my_simjob.x'
# gen_app = 'gendir/my_genjob.x'

# temp
sim_app = './my_simjob.x'

if not os.path.isfile(sim_app):
    build_simfunc()

USE_BALSAM = False  # Take as arg
# USE_BALSAM = True # Take as arg

# Create and add exes to registry
if USE_BALSAM:
    from libensemble.executors.balsam_controller import BalsamJobController
    jobctrl = BalsamJobController()
else:
    from libensemble.executors.mpi_controller import MPIJobController
    jobctrl = MPIJobController()

jobctrl.register_calc(full_path=sim_app, calc_type='sim')

# Alternative to IF could be using eg. fstring to specify: e.g:
# JOB_CONTROLLER = 'Balsam'
# registry = f"{JOB_CONTROLLER}Register()"


# --------------- Worker: sim func ----------------------------------------
# Should work with Balsam or not

def polling_loop(jobctl, job, timeout_sec=20.0, delay=2.0):
    import time
    start = time.time()

    while time.time() - start < timeout_sec:

        jobctl.manager_poll(job)

        if job.manager_signal == 'kill':
            print('Manager has sent kill signal - killing job')
            jobctl.kill(job)

        # In future might support other manager signals eg:
        elif job.manager_signal == 'pause':
            # checkpoint_job()
            pass

        time.sleep(delay)
        print('Polling at time', time.time() - start)
        job.poll()
        if job.finished:
            break
        elif job.state == 'WAITING':
            print('Job waiting to launch')
        elif job.state == 'RUNNING':
            print('Job still running ....')

    if job.finished:
        if job.state == 'FINISHED':
            print('Job finished succesfully. Status:', job.state)
        elif job.state == 'FAILED':
            print('Job failed. Status:', job.state)
        elif job.state == 'USER_KILLED':
            print('Job has been killed. Status:', job.state)
        else:
            print('Job status:', job.state)
    else:
        print("Job timed out")
        jobctl.kill(job)
        if job.finished:
            print('Now killed')
            # double check
            job.poll()
            print('Job state is', job.state)


# Tests
# ********************* NOT YET IMPLEMENTED ***********************

# From worker call JobController by different name to ensure getting registered app from JobController
jobctl = JobController.controller

print('\nTest 1 - should complete succesfully with status FINISHED :\n')
cores = 4
args_for_sim = 'sleep 5'

job = jobctl.launch(calc_type='sim', num_procs=cores, app_args=args_for_sim)
polling_loop(jobctl, job)

print('\nTest 2 - Job should be MANAGER_KILLED \n')
cores = 4
args_for_sim = 'sleep 5'

job = jobctl.launch(calc_type='sim', num_procs=cores, app_args=args_for_sim)
polling_loop(jobctl, job)
