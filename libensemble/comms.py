"""
libEnsemble communication interface
====================================================
"""

from abc import ABC, abstractmethod
import time
import queue
import numpy as np

class Timeout(Exception):
    "Communication timeout exception."
    pass


class Comm(ABC):
    """Bidirectional communication between a user func and a worker

    A comm provides a message passing abstraction for communication
    between a worker user function and the manager.  Basic messages are:

      worker(nworker) - manager tells gen that workers are available
      request(local_id, histrecs) - worker requests simulations
      queued(local_id, lo, hi) - manager assigns simulation IDs to request
      kill(id) - gen requests manager kill a simulation
      update(id, histrec) - manager informs gen of partial sim information
      result(id, histrec) - manager informs gen a sim completed
      killed(id) - manager informs gen a sim was killed

    To facilitate information sharing, we also have messages for history
    access and monitoring (for persistent gens):

      get_history(lo, hi) - gen requests history
      history(histrecs) - manager sends history
      subscribe() - gen subscribes to all history updates
    """

    @abstractmethod
    def send(self, msg_type, *args):
        "Send a message to the manager."
        pass

    @abstractmethod
    def recv(self, timeout=None):
        "Receive a message from the manager.  On timeout, return None."
        pass


class QComm(Comm):
    """Queue-based bidirectional communicator between worker and user func

    A QComm provides a message passing abstraction based on a pair of message
    queues: an inbox for incoming messages and an outbox for outgoing messages.
    These can be used with threads or multiprocessing.
    """

    def __init__(self, inbox, outbox):
        "Set the inbox and outbox queues."
        self._inbox = inbox
        self._outbox = outbox

    def send(self, msg_type, *args):
        "Place a message on the outbox queue."
        self._outbox.put((msg_type, *args))

    def recv(self, timeout=None):
        "Return a message from the inbox queue or raise TimeoutError."
        try:
            return self._inbox.get(timeout=timeout)
        except queue.Empty:
            raise Timeout()


class CommHandler(ABC):
    """Comm wrapper with message handler dispatching.

    The comm wrapper defines a message processor that dispatches to
    different handler methods based on message types.  An incoming message
    with the tag 'foo' gets dispatched to a handler 'on_foo'; if 'on_foo'
    is not defined, we pass to the 'on_unhandled_message' routine.
    """

    def __init__(self, comm):
        "Set the comm to be wrapped."
        self.comm = comm

    def send(self, msg_type, *args):
        "Send via the comm."
        self.comm.send(msg_type, *args)

    def process_message(self, timeout=None):
        "Receive and process a message via the comm."
        msg = self.comm.recv(timeout)
        msg_type, *args = msg
        try:
            method = 'on_{}'.format(msg_type)
            handler = type(self).__dict__[method].__get__(self, type(self))
        except KeyError:
            return self.on_unhandled_message(msg)
        return handler(*args)

    def on_unhandled_message(self, msg):
        "Handle any messages for which there are no named handlers."
        raise ValueError("No handler available for message {0}({1})".
                         format(msg[0], msg[1:]))


class GenCommHandler(CommHandler):
    "Wrapper for handling messages at a persistent gen."

    def send_request(self, histrecs):
        "Request new evaluations."
        self.send('request', histrecs)

    def send_kill(self, sim_id):
        "Kill an evaluation."
        self.send('kill', sim_id)

    def send_get_history(self, lo, hi):
        "Request history from manager."
        self.send('get_history', lo, hi)

    def send_subscribe(self):
        "Request subscription to updates on sims not launched by this gen."
        self.send('subscribe')

    @abstractmethod
    def on_worker(self, nworker):
        "Handle updated number of workers available to perform sims."
        pass

    @abstractmethod
    def on_queued(self, sim_id):
        "Handle sim_id assignment in response to a request"
        pass

    @abstractmethod
    def on_result(self, sim_id, hist):
        "Handle a simulation result"
        pass

    @abstractmethod
    def on_update(self, sim_id, hist):
        "Handle a simulation update"
        pass

    @abstractmethod
    def on_killed(self, sim_id):
        "Handle a simulation kill"
        pass

    @abstractmethod
    def on_history(self, hist):
        "Handle a response to a history request"
        pass


class SimCommHandler(CommHandler):
    "Wrapper for handling messages at sim."

    def send_result(self, sim_id, histrecs):
        "Send a simulation result"
        self.send('result', sim_id, histrecs)

    def send_update(self, sim_id, histrecs):
        "Send a simulation update"
        self.send('update', sim_id, histrecs)

    def send_killed(self, sim_id):
        "Send notification that a simulation was killed"
        self.send('killed', sim_id)

    @abstractmethod
    def on_request(self, sim_id, histrecs):
        "Handle a request for a simulation"
        pass

    @abstractmethod
    def on_kill(self, sim_id):
        "Handle a request to kill a simulation"
        pass


class CommEval(GenCommHandler):
    """Future-based interface for generator comms
    """

    def __init__(self, comm, workers=0, gen_specs=None):
        super().__init__(comm)
        self.sim_started = 0
        self.sim_pending = 0
        self.workers = workers
        self.gen_specs = gen_specs
        self.promises = {}
        self.returning_promises = None
        self.waiting_for_queued = 0

    def request(self, hist):
        "Request simulations, return promises"
        self.sim_started += len(hist)
        self.sim_pending += len(hist)
        self.send_request(hist)
        self.waiting_for_queued = len(hist)
        while self.waiting_for_queued > 0:
            self.process_message()
        returning_promises = self.returning_promises
        self.returning_promises = None
        return returning_promises

    def __call__(self, *args, **kwargs):
        "Request a simulation and return a promise"
        assert not (args and kwargs), \
          "Must specify simulation args by position or keyword, but not both"
        assert args or kwargs, \
          "Must specify simulation arguments."
        O = np.zeros(1, dtype=self.gen_specs['out'])
        if args:
            assert len(args) == len(self.gen_specs['out']), \
              "Wrong number of positional arguments in sim call."
            for k, spec in enumerate(self.gen_specs['out']):
                name = spec[0]
                O[name] = args[k]
        else:
            for name, value in kwargs.items():
                O[name] = value
        return self.request(O)[0]

    def wait_any(self):
        "Wait for any pending simulation to be done"
        sim_id = -1
        while sim_id < 0 or not self.promises[sim_id].done():
            sim_id = self.process_message()

    def wait_all(self):
        "Wait for all pending simulations to be done"
        while self.sim_pending > 0:
            self.process_message()

    # --- Message handlers

    def on_worker(self, nworker):
        "Update worker count"
        self.workers = nworker
        return -1

    def on_queued(self, sim_id):
        "Set up futures with indicated simulation IDs"
        lo = sim_id
        hi = sim_id + self.waiting_for_queued
        self.waiting_for_queued = 0
        self.returning_promises = []
        for s in range(lo, hi):
            promise = Future(self, s)
            self.promises[s] = promise
            self.returning_promises.append(promise)
        return -1

    def on_result(self, sim_id, hist):
        "Handle completed simulation"
        self.sim_pending -= 1
        self.promises[sim_id].on_result(hist)
        return sim_id

    def on_update(self, sim_id, hist):
        "Handle updated simulation"
        self.promises[sim_id].on_update(hist)
        return sim_id

    def on_killed(self, sim_id):
        "Handle killed simulation"
        self.sim_pending -= 1
        self.promises[sim_id].on_killed()
        return sim_id

    def on_history(self, hist):
        "Handle history message (ignored)"
        return -1


class Future:
    """Future objects for monitoring asynchronous simulation calls.

    The Future objects are not meant to be instantiated on their own;
    they are only produced by a call on a CommEval object.
    """

    def __init__(self, ceval, sim_id):
        self._ceval = ceval
        self._id = sim_id
        self._comm = ceval.comm
        self._result = None
        self._killed = False
        self._success = False

    def cancelled(self):
        "Return True if the simulation was killed."
        return self._killed

    def done(self):
        "Return True if the simulation completed successfully or was killed."
        return self._success or self._killed

    def cancel(self):
        "Cancel the simulation."
        self._ceval.send_kill(self._id)

    def result(self, timeout=None):
        "Get the result of the simulation or throw a timeout."
        while not self.done():
            if timeout is not None and timeout < 0:
                raise Timeout()
            tstart = time.time()
            try:
                self._ceval.process_message(timeout)
            except Timeout:
                pass
            if timeout is not None:
                timeout -= (time.time() - tstart)
        return self._result

    # --- Message handlers

    def on_result(self, result):
        "Handle an incoming result."
        self._result = result
        self._success = True

    def on_update(self, result):
        "Handle an incoming update."
        self._result = result

    def on_killed(self):
        "Handle a kill notification."
        self._killed = True
