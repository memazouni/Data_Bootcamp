#! /usr/bin/env python
#
# This file is part of the ghp-import package released under
# the Tumbolia Public License. See the LICENSE file for more
# information.

import errno
import optparse as op
import os
import subprocess as sp
import sys
import time
import unicodedata

__usage__ = "%prog [OPTIONS] DIRECTORY"


if sys.version_info[0] == 3:
    def enc(text):
        if isinstance(text, bytes):
            return text
        return text.encode()

    def dec(text):
        if isinstance(text, bytes):
            return text.decode('utf-8')
        return text

    def write(pipe, data):
        try:
            pipe.stdin.write(data)
        except IOError as e:
            if e.errno != errno.EPIPE:
                raise
else:
    def enc(text):
        if isinstance(text, unicode):
            return text.encode('utf-8')
        return text

    def dec(text):
        if isinstance(text, unicode):
            return text
        return text.decode('utf-8')

    def write(pipe, data):
        pipe.stdin.write(data)


def normalize_path(path):
    # Fix unicode pathnames on OS X
    # See: http://stackoverflow.com/a/5582439/44289
    if sys.platform == "darwin":
        return unicodedata.normalize("NFKC", dec(path))
    return path


def check_repo(parser):
    cmd = ['git', 'rev-parse']
    p = sp.Popen(cmd, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE)
    (ignore, error) = p.communicate()
    if p.wait() != 0:
        if not error:
            error = "Unknown Git error"
        error = error.decode("utf-8")
        if error.startswith("fatal: "):
            error = error[len("fatal: "):]
        parser.error(error)


def try_rebase(remote, branch):
    cmd = ['git', 'rev-list', '--max-count=1', '%s/%s' % (remote, branch)]
    p = sp.Popen(cmd, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE)
    (rev, ignore) = p.communicate()
    if p.wait() != 0:
        return True
    cmd = ['git', 'update-ref', 'refs/heads/%s' % branch, rev.strip()]
    if sp.call(cmd) != 0:
        return False
    return True


def get_config(key):
    p = sp.Popen(['git', 'config', key], stdin=sp.PIPE, stdout=sp.PIPE)
    (value, stderr) = p.communicate()
    return value.strip()


def get_prev_commit(branch):
    cmd = ['git', 'rev-list', '--max-count=1', branch, '--']
    p = sp.Popen(cmd, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE)
    (rev, ignore) = p.communicate()
    if p.wait() != 0:
        return None
    return rev.decode('utf-8').strip()


def mk_when(timestamp=None):
    if timestamp is None:
        timestamp = int(time.time())
    currtz = "%+05d" % (-1 * time.timezone / 36) # / 3600 * 100
    return "%s %s" % (timestamp, currtz)


def start_commit(pipe, branch, message):
    uname = dec(get_config("user.name"))
    email = dec(get_config("user.email"))
    write(pipe, enc('commit refs/heads/%s\n' % branch))
    write(pipe, enc('committer %s <%s> %s\n' % (uname, email, mk_when())))
    write(pipe, enc('data %d\n%s\n' % (len(message), message)))
    head = get_prev_commit(branch)
    if head:
        write(pipe, enc('from %s\n' % head))
    write(pipe, enc('deleteall\n'))


def add_file(pipe, srcpath, tgtpath):
    with open(srcpath, "rb") as handle:
        if os.access(srcpath, os.X_OK):
            write(pipe, enc('M 100755 inline %s\n' % tgtpath))
        else:
            write(pipe, enc('M 100644 inline %s\n' % tgtpath))
        data = handle.read()
        write(pipe, enc('data %d\n' % len(data)))
        write(pipe, enc(data))
        write(pipe, enc('\n'))


def add_nojekyll(pipe):
    write(pipe, enc('M 100644 inline .nojekyll\n'))
    write(pipe, enc('data 0\n'))
    write(pipe, enc('\n'))


def gitpath(fname):
    norm = os.path.normpath(fname)
    return "/".join(norm.split(os.path.sep))


def run_import(srcdir, branch, message, nojekyll):
    cmd = ['git', 'fast-import', '--date-format=raw', '--quiet']
    kwargs = {"stdin": sp.PIPE}
    if sys.version_info >= (3, 2, 0):
        kwargs["universal_newlines"] = False
    pipe = sp.Popen(cmd, **kwargs)
    start_commit(pipe, branch, message)
    
    for path, dnames, fnames in os.walk(srcdir):
        for fn in fnames:
            fpath = os.path.join(path, fn)
            fpath = normalize_path(fpath)
            gpath = gitpath(os.path.relpath(fpath, start=srcdir))
            add_file(pipe, fpath, gpath)
    if nojekyll:
        add_nojekyll(pipe)
    write(pipe, enc('\n'))
    pipe.stdin.close()
    if pipe.wait() != 0:
        sys.stdout.write(enc("Failed to process commit.\n"))


def main():
    sp.call("." + os.path.sep + "hugo")
    run_import("public", "gh-pages", "Updating website", True)
    sp.check_call(['git', 'push', "origin", "gh-pages"])

if __name__ == '__main__':
    # just call the main function
    main()
