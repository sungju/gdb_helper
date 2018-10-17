#!/usr/bin/env python
 
import os
import glob
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
        print "Error while reading extra packages from " + extra_filename + " : " + str(ex)

    return packages


def extract_tarfile(tarfile):
	tarname, tarext = os.path.splitext(tarfile)
	extract_opts = "xvf"
	"""
	Removing type specific extraction option as it's well handled by 'tar'

	if tarext.lower() == ".gz":
		extract_opts = "zxvf"
	if tarext.lower() == ".bz2":
		extract_opts = "jxvf"
	if tarext.lower() == ".xz":
		extract_opts = "Jxvf"
	"""
	
	command = "tar " + extract_opts + " " + tarfile
	print "Extracting abrt file with the command : " + command
	p = subprocess.Popen("tar " + extract_opts + " " + tarfile, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
	stdout, stderr = p.communicate()
	result = StringIO.StringIO(stdout)
	return result.readline().strip()
		
 
def download_debuginfo(core_path, dso_pkg_list):
	"""
yum --enablerepo='*-debug*' install $(eu-unstrip -n --core=./coredump | sed -e 's#^[^ ]* \(..\)\([^@ ]*\).*$#/usr/lib/debug/.build-id/\1/\2#p' -e 's/$/.debug/')
	"""

	# split the steps to get package list that needs to be installed.
	pkg_list_command = "eu-unstrip -n --core={0}coredump | sed -e 's#^[^ ]* \\(..\\)\\([^@ ]*\\).*$#/usr/lib/debug/.build-id/\\1/\\2#p' -e 's/$/.debug/'".format(core_path)
	p = subprocess.Popen(pkg_list_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
	stdout, stderr = p.communicate()
	pkg_list = stdout.split()
	pkg_list.extend(dso_pkg_list)

	pkg_list_command = "eu-unstrip -n --core={0}coredump | awk '{{ print $5 }}'".format(core_path)
	p = subprocess.Popen(pkg_list_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
	stdout, stderr = p.communicate()
	pkg_name_list = stdout.split()

	command_template = "sudo yum --enablerepo='*-debug*' install --setopt=protected_multilib=false "

	print "Downloading and installing debuginfo packages by extracting data from " + core_path + "coredump"
	count = 0
	total = len(pkg_name_list)
	for pkg in pkg_name_list:
		normal_pkg = pkg_list[count]
		debug_pkg = pkg_list[count + 1]
		count = count + 2
		print "(%d/%d) %s (%s)" % (count / 2, total, pkg, normal_pkg)
		command = command_template + normal_pkg + debug_pkg
		p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
		stdout, stderr = p.communicate()
		if stderr.find("Error: Nothing to do") != -1:
			pass #print "Already installed"
		elif stderr != "":
			print stderr
		else:
			pass # print "Installed"

"""
	command = "sudo yum --enablerepo='*-debug*' install $(eu-unstrip -n --core={0}coredump | sed -e 's#^[^ ]* \\(..\\)\\([^@ ]*\\).*$#/usr/lib/debug/.build-id/\\1/\\2#p' -e 's/$/.debug/')".format(core_path)
	p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
	stdout, stderr = p.communicate()
	#print stdout
	print stderr
	"""
 
 
def get_package_list_from_dso(dso_path):
	try:
		file = open(dso_path + "dso_list", "r")
		try:
			lines = file.readlines()
		finally:
			file.close()
	except Exception, ex:
		print "Error while reading 'dso_list' : " + str(ex)

	package_list = []
	rpm_list = []
	for line in lines:
		pkgname = line.split()[1]
		package_list.append(pkgname)
		rpm_list.append(pkgname.replace(":", ".") + ".rpm")
 
	#print " ".join(package_list)
	return {'package': package_list, 'rpm': rpm_list}
 
def download_rpms(package_dict, workpath):
	print ""
	print "Downloading binary RPMs into " + workpath
	rpm_list = package_dict['package']
	count = 0
	total = len(rpm_list)
	downloaded_rpm_list = []
	for rpm in rpm_list:
		count = count + 1
		print("(%d/%d) : %s" % (count, total, rpm))
		command = "cd " + workpath + "; sudo yumdownloader " + rpm
		p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
		stdout, stderr = p.communicate()
		
def extract_rpms(extract_path):
	print ""
	print "Extracting rpm packages:"
	os.chdir(extract_path)
	rpm_list = glob.glob("*.rpm")
	count = 0
	total = len(rpm_list)
	for rpm in rpm_list:
		#print rpm, extract_path
		count = count + 1
		print("(%d/%d) : %s" % (count, total, rpm))
		command = "cd {0}; rpm2cpio {1} | cpio -idmu".format(extract_path, rpm)
		p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
		stdout, stderr = p.communicate()
	os.chdir("..")

def readlines_from_pipe(pipe):
	result = ''
	while pipe.poll() is None:
		try:
			result += pipe.stdout.read()
		except IOError:
			if result.find("(gdb)") >= 0:
				break

	return result
 
def start_gdb(core_path, extract_path):
	"""
set solib-absolute-prefix ./usr
file path/to/executable
core-file path/to/corefile
	"""
 
	try:
		f = open(core_path + "executable", "r")
		try:
			cmd = f.readline()
		finally:
			f.close()
	except Exception, ex:
		print "Error while reading 'executable' : " + str(ex)

	cmdpath = extract_path + cmd
	"""
	gdb_execute = "gdb {0} --core={1}coredump".format(cmdpath, core_path)
	print gdb_execute
	os.system(gdb_execute)
	"""
	setsolib = "set solib-absolute-prefix " + extract_path
	execload = "file " + cmdpath
	coreload = "core-file " + core_path + "coredump"
	gdbcommand = setsolib + "\n" + execload + "\n" + coreload
	#print 
	#print "Please run the below commands in gdb prompt"
	#print "-------------------------------------------"
	#print gdbcommand
	#print
	gdb_start_cmds = [setsolib, execload, coreload]

	try:
		f = open("gdb_cmd.txt", "w+")
		try:
			f.write(setsolib + "\n")
			f.write(execload + "\n")
			f.write(coreload + "\n")
		finally:
			f.close()
	except Exception, ex:
		print "Error to save command list in file cmd.txt : " + str(ex)
 
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
	usage = "usage: %prog [options] [abrt file]\n\nThis script help to build gdb environment for a coredump collected via 'abrt'\n\nIf [abrt file] is provided, it will ignore '-c|--core' option\n"
	parser = OptionParser(usage)
	parser.add_option("-c", "--core", dest="corepath",
			  help="path for coredump and related files")
	parser.add_option("-w", "--work", dest="workpath",
			  help="path for temporary rpm binaries") 
	parser.add_option("-e", "--extra", dest="extra",
				            help="file that contains extra package list you want to install. Useful when core doesn't specify some packages you need to have")


	corepath = "./"
	workpath = "./tempdir"
	tarfile = ""
	(options, args) = parser.parse_args()

	if options.corepath:
		corepath = options.corepath

	if options.workpath:
		workpath = options.workpath

	if len(args) > 0:
		tarfile = args[0]
 
	try:
		os.mkdir(extract_path)
	except Exception, e:
		pass

	try:
		os.mkdir(workpath)
	except Exception, e:
		pass

	if tarfile != "":
		path = extract_tarfile(tarfile)
		if path != "":
			corepath = path

	extra_list = []
	if options.extra:
		extra_list = get_extra_package_list(options.extra)

	pkg_list = get_package_list_from_dso(corepath)
	pkg_list['package'].extend(extra_list)
	pkg_list['rpm'].extend(extra_list)

	download_debuginfo(corepath, pkg_list['package'])
	download_rpms(pkg_list, workpath)
	extract_rpms(workpath)
	#extract_rpms(pkg_list['rpm'], workpath)
	start_gdb(corepath, workpath)
 
if __name__ == "__main__":
	main()

