# """
# Runs libEnsemble testing timeout and wait for persistent worker.
#
# Execute via one of the following commands (e.g. 3 workers):
#    mpiexec -np 4 python3 test_6-test_persistent_aposmm_timeout.py
#    python3 test_6-test_persistent_aposmm_timeout.py --nworkers 3 --comms local
#    python3 test_6-test_persistent_aposmm_timeout.py --nworkers 3 --comms tcp
#
# The number of concurrent evaluations of the objective function will be 4-1=3.
# """

# Do not change these lines - they are parsed by run-tests.sh
# TESTSUITE_COMMS: local mpi tcp
# TESTSUITE_NPROCS: 4
# TESTSUITE_EXTRA: true

import sys
import numpy as np

# Import libEnsemble items for this test
from libensemble.libE import libE
from libensemble.sim_funcs.periodic_func import func_wrapper as sim_f
from libensemble.gen_funcs.persistent_aposmm import aposmm as gen_f
from libensemble.alloc_funcs.persistent_aposmm_alloc import persistent_aposmm_alloc as alloc_f
from libensemble.tools import parse_args, add_unique_random_streams, save_libE_output

nworkers, is_manager, libE_specs, _ = parse_args()

if nworkers < 2:
    sys.exit("Cannot run with a persistent worker if only one worker -- aborting...")

n = 2
sim_specs = {'sim_f': sim_f,
             'in': ['x'],
             'out': [('f', float)]}

gen_out = [('x', float, n), ('x_on_cube', float, n), ('sim_id', int),
           ('local_min', bool), ('local_pt', bool)]

gen_specs = {'gen_f': gen_f,
             'in': [],
             'out': gen_out,
             'user': {'initial_sample_size': 100,
                      'localopt_method': 'LN_BOBYQA',
                      'xtol_abs': 1e-8,
                      'ftol_abs': 1e-8,
                      'run_max_eval': 30,
                      'lb': np.array([0, -np.pi/2]),
                      'ub': np.array([2*np.pi, 3*np.pi/2]),
                      'periodic': True,
                      'print': True
                      }
             }

alloc_specs = {'alloc_f': alloc_f, 'out': [], 'user': {}}

# Setting a very high sim_max value and a short elapsed_wallclock_time so timeout will occur
exit_criteria = {'sim_max': 50000, 'elapsed_wallclock_time': 5}

persis_info = add_unique_random_streams({}, nworkers + 1)

# Perform the run
H, persis_info, flag = libE(sim_specs, gen_specs, exit_criteria, persis_info,
                            alloc_specs, libE_specs)

if is_manager:
    assert flag == 2, "Test should have timed out"
    assert persis_info[1].get('run_order'), "Run_order should have been given back"
    min_ids = np.where(H['local_min'])
    save_libE_output(H, persis_info, __file__, nworkers)
