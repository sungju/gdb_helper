#!/usr/bin/env python
 
import os
import fcntl
import sys
import subprocess
import re
import time
from optparse import OptionParser
import StringIO
 

def get_extra_package_list(extra_filename):
	"""
	file contains debug package names in each line
	"""
	try:
		file = open(extra_filename, "r")
		try:
			packages = file.readlines()
		finally:
			file.close()
	except Exception, ex:
		print "Error while reading extra packages from " + extra_filename + " : " + ex.strerror

	return packages

def get_package_list(core_path):
	"""
yum --enablerepo='*-debug*' install $(eu-unstrip -n --core=./coredump | sed -e 's#^[^ ]* \(..\)\([^@ ]*\).*$#/usr/lib/debug/.build-id/\1/\2#p' -e 's/$/.debug/') --setopt=protected_multilib=false
	"""

	pkg_list_command = "sudo yum --enablerepo='*' --enablerepo='*-debug*' install --setopt=protected_multilib=false $(eu-unstrip -n --core={0} | sed -e 's#^[^ ]* \\(..\\)\\([^@ ]*\\).*$#/usr/lib/debug/.build-id/\\1/\\2#p' -e 's/$/.debug/')".format(core_path)
	print "EXEC> " + pkg_list_command
	p = subprocess.Popen(pkg_list_command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
	check_pkg_list = 0
	pkg_list = []
	while p.poll() is None:
		output = p.stdout.readline()
		print output,
		if output.startswith("Package matching"):
			pkg_list.append(output.split()[2])
			continue
		elif output.find("already installed") > 0:
			pkg_list.append(output.split()[1])
			continue

		if output.startswith("Total download"):
			p.stdin.write("\n")
		if output.startswith("Installing"):
			check_pkg_list = 1
			continue
		if output.startswith("Updating"):
			continue
		if output.startswith("Transaction"):
			check_pkg_list = 0

		if check_pkg_list == 1 and output.startswith(" "):
			pkgdetail = output.split()
			if (len(pkgdetail) == 1):
				output = p.stdout.readline()
				print output
				extra_detail = output.split()
				pkgdetail.extend(extra_detail)
			if (len(pkgdetail) > 3):
				if pkgdetail[0].endswith(pkgdetail[1]):
					pkgdetail[0] = pkgdetail[0].replace("-" + pkgdetail[1], "")
				pkgname = "%s-%s.%s" % (pkgdetail[0], pkgdetail[2], pkgdetail[1])
				pkg_list.append(pkgname)

	return pkg_list

def get_full_package_list(pkg_list):
	pkg_debug_names = " ".join(pkg_list)
	pkg_names = " ".join(pkg_list)
	full_pkg_names = pkg_debug_names + " " + pkg_names.replace("-debuginfo-", "-")
	full_pkg_names.replace('\n', '')
	return full_pkg_names.split()


def download_rpms(pkg_list, workpath):
	full_pkg_names = " ".join(get_full_package_list(pkg_list))
	pkg_download_command = "cd %s; sudo yumdownloader --enablerepo='*' --enablerepo='*-debug*' %s" % (workpath, full_pkg_names)
	print "EXEC> " + pkg_download_command
	p = subprocess.Popen(pkg_download_command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)	
	while p.poll() is None:
		output = p.stdout.readline()
		print output,

def extract_rpms(pkg_list, workpath):
	print ""
	print "Extracting rpm packages:"
	full_pkg_list = get_full_package_list(pkg_list)
	count = 0
	total = len(full_pkg_list)
	for rpm in full_pkg_list:
		#print rpm, extract_path
		count = count + 1
		print("(%d/%d) : %s.rpm" % (count, total, rpm))
		command = "cd {0}; rpm2cpio {1}.rpm | cpio -idmu".format(workpath, rpm)
		p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
		stdout, stderr = p.communicate()
        #print stderr


def readlines_from_pipe(pipe):
	result = ''
	while pipe.poll() is None:
		try:
			result += pipe.stdout.read()
		except IOError:
			if result.find("(gdb)") >= 0:
				break

	return result


def start_gdb(corepath, workpath):
	"""
set solib-absolute-prefix ./usr
file path/to/executable
core-file path/to/corefile
	"""
	command = "file {0}".format(corepath)
	p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
	stdout, stderr = p.communicate()
	print stdout
	cmd = stdout[stdout.index("from '") + 6:-2]
	print cmd

	command = "strings {0} | grep '/{1}$' | grep '^/'".format(corepath, cmd.split()[0])
	p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
	stdout, stderr = p.communicate()
	print stdout
	cmdpath = workpath + stdout.split('\n')[0]

 
	"""
	gdb_execute = "gdb {0} --core={1}".format(cmdpath, corepath)
	print gdb_execute
	os.system(gdb_execute)
	"""
	setsolib = "set solib-absolute-prefix " + workpath
	execload = "file " + cmdpath
	coreload = "core-file " + corepath
	#gdbcommand = setsolib + "\n" + execload + "\n" + coreload
	#print 
	#print "Please run the below commands in gdb prompt"
	#print "-------------------------------------------"
	#print gdbcommand
	#print

	gdb_start_cmds = [setsolib, execload, coreload]
 
#	os.system("gdb --quiet")
	gdb_command = ["gdb", "--quiet"]
	p = subprocess.Popen(gdb_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
	fcntl.fcntl(p.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
	for i in gdb_start_cmds:
		print readlines_from_pipe(p).strip() + i + '\n'
		p.stdin.write(i + '\n')
		p.stdin.flush()

	while True:
		print '\r' + readlines_from_pipe(p),
		if p.poll() is not None:
			break
		input = sys.stdin.readline()
		p.stdin.write(input)
		p.stdin.flush()


def main():
	usage = "usage: %prog [options]\n\nSet the GDB environment with core only"
	parser = OptionParser(usage)
	parser.add_option("-c", "--core", dest="corepath",
			  help="path for coredump")
	parser.add_option("-w", "--work", dest="workpath",
			  help="path for temporary rpm binaries") 
	parser.add_option("-e", "--extra", dest="extra",
			help="file that contains extra package list you want to install. Useful when core doesn't specify some packages you need to have")

	corepath = "./"
	workpath = "./tempdir"
	(options, args) = parser.parse_args()

	if options.corepath:
		corepath = options.corepath

	if options.workpath:
		workpath = options.workpath

	try:
		os.mkdir(workpath)
	except Exception, e:
		pass

	extra_list = []
	if options.extra:
		extra_list = get_extra_package_list(options.extra)
	pkg_list = get_package_list(corepath)
	pkg_list.extend(extra_list)
	print pkg_list
	download_rpms(pkg_list, workpath)
	extract_rpms(pkg_list, workpath)
	start_gdb(corepath, workpath)
 
if __name__ == "__main__":
	main()

