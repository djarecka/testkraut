# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the testkraut package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'

import os
import re
import subprocess
import select
import datetime
import hashlib

def which(program):
    """
    http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
    """
    def is_exe(fpath):
        return os.path.exists(fpath) and os.access(fpath, os.X_OK)

    def ext_candidates(fpath):
        yield fpath
        for ext in os.environ.get("PATHEXT", "").split(os.pathsep):
            yield fpath + ext

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            for candidate in ext_candidates(exe_file):
                if is_exe(candidate):
                    return candidate

    return None


class Stream(object):
    # this has been taken from Nipype (BSD-3-clause license)
    """Function to capture stdout and stderr streams with timestamps

    http://stackoverflow.com/questions/4984549/merge-and-sync-stdout-and-stderr/5188359#5188359
    """

    def __init__(self, name, impl):
        self._name = name
        self._impl = impl
        self._buf = ''
        self._rows = []
        self._lastidx = 0

    def fileno(self):
        "Pass-through for file descriptor."
        return self._impl.fileno()

    def read(self, drain=0):
        "Read from the file descriptor. If 'drain' set, read until EOF."
        while self._read(drain) is not None:
            if not drain:
                break

    def _read(self, drain):
        "Read from the file descriptor"
        fd = self.fileno()
        buf = os.read(fd, 4096)
        if not buf and not self._buf:
            return None
        if '\n' not in buf:
            if not drain:
                self._buf += buf
                return []

        # prepend any data previously read, then split into lines and format
        buf = self._buf + buf
        if '\n' in buf:
            tmp, rest = buf.rsplit('\n', 1)
        else:
            tmp = buf
            rest = None
        self._buf = rest
        now = datetime.datetime.now().isoformat()
        rows = tmp.split('\n')
        self._rows += [(now, '%s %s:%s' % (self._name, now, r), r) for r in rows]
        self._lastidx = len(self._rows)



def run_command(cmdline, cwd=None, env=None, timeout=0.01):
    # this has been taken from Nipype (BSD-3-clause license)
    """
    Run a command, read stdout and stderr, prefix with timestamp. The returned
    runtime contains a merged stdout+stderr log with timestamps

    http://stackoverflow.com/questions/4984549/merge-and-sync-stdout-and-stderr/5188359#5188359
    """
    PIPE = subprocess.PIPE
    proc = subprocess.Popen(cmdline,
                            stdout=PIPE,
                            stderr=PIPE,
                            shell=True,
                            cwd=cwd,
                            env=env)
    streams = [
        Stream('stdout', proc.stdout),
        Stream('stderr', proc.stderr)
        ]

    def _process(drain=0):
        try:
            res = select.select(streams, [], [], timeout)
        except select.error, e:
            if e[0] == errno.EINTR:
                return
            else:
                raise
        else:
            for stream in res[0]:
                stream.read(drain)

    while proc.returncode is None:
        proc.poll()
        _process()
    returncode = proc.returncode
    _process(drain=1)

    # collect results, merge and return
    result = {}
    temp = []
    for stream in streams:
        rows = stream._rows
        temp += rows
        result[stream._name] = [r[2] for r in rows]
    temp.sort()
    result['merged'] = [r[1] for r in temp]
    result['retval'] = returncode
    return result

def get_shlibdeps(binary):
    # for now only unix
    cmd = 'ldd %s' % binary
    ret = run_command(cmd)
    if not ret['retval'] == 0:
        raise RuntimeError("An error occurred while executing '%s'\n%s"
                           % (cmd, '\n'.join(ret['stderr'])))
    else:
        deps = [re.match(r'.*=> (.*) \(.*', l) for l in ret['stdout']]
        return [d.group(1) for d in deps if not d is None and len(d.group(1))]

def get_script_interpreter(filename):
    shebang = open(filename).readline()
    match = re.match(r'^#!(.*)$', shebang)
    if match is None:
        raise ValueError("no valid shebang line found in '%s'" % filename)
    return match.group(1).strip()

def hash(filename, method):
    hash = method
    with open(filename,'rb') as f: 
        for chunk in iter(lambda: f.read(128*hash.block_size), b''): 
             hash.update(chunk)
    return hash.hexdigest()

def sha1sum(filename):
    return hash(filename, hashlib.sha1())

def md5sum(filename):
    return hash(filename, hashlib.md5())

def get_debian_pkg(filename):
    # provided by a Debian package?
    pkgname = None
    try:
        ret = run_command('dpkg -S %s' % filename)
    except OSError:
        return None
    if not ret['retval'] == 0:
        return None
    for line in ret['stdout']:
        lspl = line.split(':')
        if lspl[0].count(' '):
            continue
        pkgname = lspl[0]
        break
    return pkgname

def _get_next_pid_id(procs, pid):
    base_pid = pid
    pid_suffix = 0
    while pid in procs:
        pid = '%s.%i' % (base_pid, pid_suffix)
        pid_suffix += 1
    return pid

def _find_parent_with_argv(procs, proc):
    if proc['started_by'] is None:
        raise ValueError("no information on parent process in '%s'" % proc)
    parent_proc = procs[proc['started_by']]
    if not parent_proc['argv'] is None:
        return parent_proc['pid']
    else:
        return _find_parent_with_argv(procs, parent_proc)

def _get_new_proc(procs, pid):
    oldpid = None
    if pid in procs:
        # archive a potentially existing proc of this PID under a safe
        # new PID
        oldpid = _get_next_pid_id(procs, pid)
        proc = procs[pid]
        proc['pid'] = oldpid
        procs[oldpid] = proc
    proc = dict(dict(pid=pid, started_by=None, argv=None,
                     uses=[], generates=[]))
    procs[pid] = proc
    return proc, oldpid

def get_cmd_prov_strace(cmd):
    cmd_prefix = ['strace', '-q', '-f', '-s', '1024',
                  '-e', 'trace=execve,clone,open,openat,unlink,unlinkat']
    cmd = cmd_prefix + cmd
    cmd_exec = subprocess.Popen(cmd, bufsize=0,
                             stderr=subprocess.PIPE)
    # store discovered processes
    procs = {}
    # store accessed files
    files = {}
    curr_proc = None
    # precompile REs
    quoted_list_splitter = re.compile(r'(?:[^,"]|"[^"]*\")+')
    syscall_arg_splitter = re.compile(r'(?:[^,[]|\[[^]]*\])+')
    #strace_ouput_splitter = re.compile(r'^(\[pid\s+([0-9]+)\] |)([a-z0-9_]+)\((.*)\) (.*)')
    strace_output_splitter = re.compile(r'^(\[pid\s+([0-9]+)\] |)([a-z0-9_]+)\((.*)')
    strace_resume_splitter = re.compile(r'^(\[pid\s+([0-9]+)\] |)<\.\.\. ([a-z0-9_]+) resumed> (.*)')
    unfinished_splitter = re.compile(r'(.*)\s+<unfinished \.\.\.>')
    rest_splitter = re.compile(r'(.*)\s+=\s+(.*)')
    # for every line in strace's output
    root_pid = None
    unfinished = {}
    for line in cmd_exec.stderr:
        match = strace_output_splitter.match(line)
        if match is None:
            # this could be a resume line
            match = strace_resume_splitter.match(line)
            if match is None:
                # ignore funny line
                continue
            # we have a resume, check if we know the beginning of it
            _, pid, syscall, rest = match.groups()
            if pid in unfinished:
                pdict = unfinished[pid]
                if syscall in pdict:
                    start = pdict[syscall]
                    del pdict[syscall]
                else:
                    raise RuntimeError("no resume info on started syscall (%s, %s)"
                                       % (syscall, pid))
                if not len(pdict):
                    del unfinished[pid]
            else:
                raise RuntimeError("no resume info on pid %s"
                                   % pid)
            rest = '%s %s' % (start, rest)
        else:
            #_, pid, syscall, syscall_args, syscall_ret = match.groups()
            _, pid, syscall, rest = match.groups()
            umatch = unfinished_splitter.match(rest)
            if not umatch is None:
                # this is the start of an unfinished syscall
                pdict = unfinished.get(pid, dict())
                pdict[syscall] = umatch.group(1)
                unfinished[pid] = pdict
                continue # will be processed on resume
        syscall_args, syscall_ret = rest_splitter.match(rest).groups()
        if not pid is None and not pid == root_pid and not pid in procs:
            if not root_pid is None:
                raise RuntimeError("we already have a root PID, and found a new one")
            root_pid = pid
        if pid is None:
            pid = 'mother'
        if syscall_ret.startswith('-'):
            # ignore any syscall that yielded an error
            continue
        # everything we know about this process
        if not pid in procs:
            proc, _ = _get_new_proc(procs, pid)
        else:
            proc = procs[pid]
        # split the syscall args into a list
        syscall_args = syscall_arg_splitter.findall(syscall_args)
        if syscall == 'clone':
            newpid = syscall_ret
            # it started a new proc
            new_proc, _ = _get_new_proc(procs, newpid)
            new_proc['started_by'] = pid
        elif syscall == 'execve':
            # start a process
            executable = syscall_args[0].strip('"')
            argv = [arg.strip(' "') for arg in
                        quoted_list_splitter.findall(syscall_args[1].strip(' []'))]
            if not proc['argv'] is None:
                # a new command in the same process -> code as a new process)
                new_proc, oldpid = _get_new_proc(procs, pid)
                new_proc['started_by'] = oldpid
                proc = new_proc
            proc.update(dict(executable=executable,
                             argv=argv))
        elif syscall == 'open':
            # open a file
            open_args = [arg.strip(' "') for arg in syscall_args]
            filename = os.path.relpath(open_args[0])
            access_mode = open_args[1]
            if filename.startswith(os.path.pardir):
                # track files under the current dir only
                continue
            if 'O_WRONLY' in access_mode or 'O_RDWR' in access_mode:
                proc['generates'].append(filename)
            elif 'O_RDONLY' in access_mode or 'O_RDWR' in access_mode:
                proc['uses'].append(filename)
        else:
            # ignore all other syscalls
            pass
    # rewrite PID of the root process if we got to know it
    if not root_pid is None:
        # merge the info of root_pid with the mother's
        rproc = procs[root_pid]
        for pid, proc in procs.iteritems():
            if pid.startswith('mother'):
                for attr in ('generates', 'uses'):
                    proc[attr] += rproc[attr]
                    proc[attr] = [a.replace('mother', root_pid)
                                    for a in proc[attr]]
                proc['pid'] = pid.replace('mother', root_pid)
            for attr in ('started_by',):
                if not proc[attr] is None:
                    proc[attr] = proc[attr].replace('mother', root_pid)
            #REPLACE ALL MOTHER REFERENCES IN ALL ATTRS
        del procs[root_pid]
        procs = dict([(pid.replace('mother', root_pid), info) for pid, info in procs.iteritems()])
    # uniquify
    for pid, proc in procs.iteritems():
        for attr in ('generates', 'uses'):
            proc[attr] = set(proc[attr])
    # rewrite inter-proc dependencies to point to processes with cmdinfo
    pid_mapper = {}
    for pid, proc in procs.iteritems():
        if proc['started_by'] is None:
            # nothing to recode
            continue
        # we have a parent process, but we might have no cmd info
        # -> retrace graph upwards to find a parent with info
        parent_pid = proc['started_by']
        new_parent_pid = pid_mapper.get(parent_pid,
                                        _find_parent_with_argv(procs, proc))
        # cache pid mapping: old parent -> new parent
        # (even if it woudl be the same)
        pid_mapper[parent_pid] = new_parent_pid
        # rewrite parent in current process
        proc['started_by'] = new_parent_pid
        if proc['argv'] is None:
            # we don't want to know about this process
            # move the files it uses and generates upwards
            new_parent_proc = procs[new_parent_pid]
            for field in ('uses', 'generates'):
                new_parent_proc[field] = new_parent_proc[field].union(proc[field])
        else:
            # this proc info stays
            pid_mapper[pid] = pid
    # filter all procs that have no argv
    procs = dict([(pid, procs[pid]) for pid in pid_mapper.values()])
    # wait() sets the returncode
    cmd_exec.wait()
    return procs, cmd_exec.returncode
