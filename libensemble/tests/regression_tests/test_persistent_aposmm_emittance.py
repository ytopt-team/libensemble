"""
Runs libEnsemble with APOSMM+IBCDFO on a synthetic "beamline simulation"
function (taking in 4 variables and returning three outputs to represent
position <x>, momentum <p_x>, and the correlation between them <x p_x>).

These values are then mapped to the normalized emittance <x> <p_x> - <x p_x>.

Execute via one of the following commands:
   mpiexec -np 3 python test_persistent_aposmm_emittance.py
   python test_persistent_aposmm_emittance.py --nworkers 2 --comms local
Both will run with 1 manager, 1 worker running APOSMM+IBCDFO), and 1 worker
doing the simulation evaluations.
"""

# Do not change these lines - they are parsed by run-tests.sh
# TESTSUITE_COMMS: local mpi
# TESTSUITE_NPROCS: 3

import multiprocessing
import sys

import numpy as np

import libensemble.gen_funcs
from libensemble.libE import libE

libensemble.gen_funcs.rc.aposmm_optimizers = "ibcdfo"

from libensemble.alloc_funcs.persistent_aposmm_alloc import persistent_aposmm_alloc as alloc_f
from libensemble.gen_funcs.persistent_aposmm import aposmm as gen_f
from libensemble.tools import add_unique_random_streams, parse_args, save_libE_output

try:
    from ibcdfo.pounders import pounders  # noqa: F401
    from ibcdfo.pounders.general_h_funs import emittance_combine, emittance_h
except ModuleNotFoundError:
    sys.exit("Please 'pip install ibcdfo'")

try:
    from minqsw import minqsw  # noqa: F401

except ModuleNotFoundError:
    sys.exit("Ensure https://github.com/POptUS/minq has been cloned and that minq/py/minq5/ is on the PYTHONPATH")


def synthetic_beamline_mapping(H, _, sim_specs):
    x = H["x"][0]
    assert len(x) == 4, "Assuming 4 inputs to this function"
    y = np.zeros(3)  # Synthetic beamline outputs
    y[0] = x[0] ** 2 + 1.0
    y[1] = x[1] ** 2 + 2.0
    y[2] = x[2] * x[3] + 0.5

    Out = np.zeros(1, dtype=sim_specs["out"])
    Out["fvec"] = y
    Out["f"] = y[0] * y[1] - y[2] ** 2
    return Out


# Main block is necessary only when using local comms with spawn start method (default on macOS and Windows).
if __name__ == "__main__":
    multiprocessing.set_start_method("fork", force=True)

    nworkers, is_manager, libE_specs, _ = parse_args()

    assert nworkers == 2, "This test is just for two workers"

    # Declare the run parameters/functions
    m = 3
    n = 4

    sim_specs = {
        "sim_f": synthetic_beamline_mapping,
        "in": ["x"],
        "out": [("f", float), ("fvec", float, m)],
    }

    gen_out = [
        ("x", float, n),
        ("x_on_cube", float, n),
        ("sim_id", int),
        ("local_min", bool),
        ("local_pt", bool),
        ("started_run", bool),
    ]

    gen_specs = {
        "gen_f": gen_f,
        "persis_in": ["f", "fvec"] + [n[0] for n in gen_out],
        "out": gen_out,
        "user": {
            "initial_sample_size": 1,
            "max_active_runs": 1,
            "sample_points": np.array([[0.1, 0.2, 0.345, 0.56]]),
            "localopt_method": "ibcdfo_pounders",
            "components": m,
            "hfun": emittance_h,
            "combinemodels": emittance_combine,
            "lb": -1 * np.ones(n),
            "ub": np.ones(n),
        },
    }

    alloc_specs = {"alloc_f": alloc_f}

    persis_info = add_unique_random_streams({}, nworkers + 1)

    exit_criteria = {"sim_max": 500}

    # Perform the run
    H, persis_info, flag = libE(sim_specs, gen_specs, exit_criteria, persis_info, alloc_specs, libE_specs)

    if is_manager:
        assert persis_info[1].get("run_order"), "Run_order should have been given back"
        assert flag == 0

        save_libE_output(H, persis_info, __file__, nworkers)

        from libensemble.sim_funcs.chwirut1 import EvaluateFunction, EvaluateJacobian

        for i in np.where(H["local_min"])[0]:
            F = EvaluateFunction(H["x"][i])
            J = EvaluateJacobian(H["x"][i])
            # u = gen_specs["user"]["ub"] - H["x"][i]
            # l = H["x"][i] - gen_specs["user"]["lb"]
            # if np.any(u <= 1e-7) or np.any(l <= 1e-7):
            #     grad = -2 * np.dot(J.T, F)
            #     assert np.all(grad[u <= 1e-7] >= 0)
            #     assert np.all(grad[l <= 1e-7] <= 0)

            #     if not np.all(grad[np.logical_and(u >= 1e-7, l >= 1e-7)] <= 1e-5):
            #         import ipdb

            #         ipdb.set_trace()
            # else:
            #     d = np.linalg.solve(np.dot(J.T, J), np.dot(J.T, F))
            #     assert np.linalg.norm(d) <= 1e-5
