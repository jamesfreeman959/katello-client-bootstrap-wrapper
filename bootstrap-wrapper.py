import os
import platform
import socket
import sys
import urllib2
import pwd
import getpass
import subprocess
from optparse import OptionParser
from urllib import urlencode
from ConfigParser import SafeConfigParser
from datetime import datetime

"""Colors to be used by the multiple `print_*` functions."""
error_colors = {
    'HEADER': '\033[95m',
    'OKBLUE': '\033[94m',
    'OKGREEN': '\033[92m',
    'WARNING': '\033[93m',
    'FAIL': '\033[91m',
    'ENDC': '\033[0m',
}

def print_generic(msg):
    """Helper function to output a NOTIFICATION message."""
    print "[NOTIFICATION], [%s], [%s] " % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg)

def print_error(msg):
    """Helper function to output an ERROR message."""
    print "[%sERROR%s], [%s], EXITING: [%s] failed to execute properly." % (error_colors['FAIL'], error_colors['ENDC'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg)


# curl https://satellite.example.com:9090/ssh/pubkey >> ~/.ssh/authorized_keys
# sort -u ~/.ssh/authorized_keys
def install_foreman_ssh_key():
    """
    Download and install the Satellite's SSH public key into the foreman user's
    authorized keys file, so that remote execution becomes possible.
    """
    try:
        userpw = pwd.getpwnam(options.remote_exec_user)
    except KeyError:
        print_generic("User %s does not exist - adding." % options.remote_exec_user)
        try:
            subprocess.call(["useradd","-m",options.remote_exec_user])
        except:
            print_error("useradd command failed.")
            sys.exit(1)
        else:
            print_generic("Successfully added user %s" % options.remote_exec_user)
    else:
        print_generic("User %s already exists - proceeding" % options.remote_exec_user)

def run_bootstrap():
    try:
        bootstrap_py = urllib2.urlopen("https://%s/pub/bootstrap.py" % options.foreman_fqdn).read()
    except urllib2.HTTPError, e:
        print_generic("The server was unable to fulfill the request. Error: %s - %s" % (e.code, e.reason))
        print_generic("Please ensure the Satellite/Capsule FQDN is correctly specified and reachable")
        return
    except urllib2.URLError, e:
        print_generic("Could not reach the server. Error: %s" % e.reason)
        return
    output = os.fdopen(os.open("bootstrapd.py", os.O_WRONLY | os.O_CREAT, 0600), 'a')
    output.write(bootstrap_py)
    print_generic("bootstrap.py downloaded successfully")
    output.close()

    # Get the current arguments from the wrapper script as these will be passed to the original bootstrap script 
    # Perform any required processing on these arguments too...
    bootstrap_cmd = sys.argv
    # Change element 0 in the list (current script name) to be our downloaded bootstrap script - all other elements 
    # are the original arguments and remain the same
    bootstrap_cmd[0] = os.path.dirname(__file__) + "/bootstrapd.py"
    # Insert the command python as element 0 in the list, shifting all other elements to the right
    # Necessary because the bootstrap script itself isn't executable directly
    bootstrap_cmd.insert(0, "python")
    print(bootstrap_cmd)
    try:
        subprocess.call(bootstrap_cmd)
    except:
        print_error("Error running bootstrap script")
    else:
        print_generic("Completed run of external bootstrap script")
 

def clean_environment():
    """
    Undefine `GEM_PATH`, `LD_LIBRARY_PATH` and `LD_PRELOAD` as many environments
    have it defined non-sensibly.
    """
    for key in ['GEM_PATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD']:
        os.environ.pop(key, None)

def get_architecture():
    """
    Helper function to get the architecture x86_64 vs. x86.
    """
    return os.uname()[4]


class BetterHTTPErrorProcessor(urllib2.BaseHandler):
    """
    A substitute/supplement class to urllib2.HTTPErrorProcessor
    that doesn't raise exceptions on status codes 201,204,206
    """
    def http_error_201(self, request, response, code, msg, hdrs):
        return response

    def http_error_204(self, request, response, code, msg, hdrs):
        return response

    def http_error_206(self, request, response, code, msg, hdrs):
        return response


if __name__ == '__main__':

    # > Register our better HTTP processor as default opener for URLs.
    opener = urllib2.build_opener(BetterHTTPErrorProcessor)
    urllib2.install_opener(opener)

    # > Gather MAC Address.
    MAC = None
    try:
        import uuid
        mac1 = uuid.getnode()
        mac2 = uuid.getnode()
        if mac1 == mac2:
            MAC = ':'.join(("%012X" % mac1)[i:i + 2] for i in range(0, 12, 2))
    except ImportError:
        if os.path.exists('/sys/class/net/eth0/address'):
            address_files = ['/sys/class/net/eth0/address']
        else:
            address_files = glob.glob('/sys/class/net/*/address')
        for f in address_files:
            MAC = open(f).readline().strip().upper()
            if MAC != "00:00:00:00:00:00":
                break
    if not MAC:
        MAC = "00:00:00:00:00:00"

    # > Gather API port (HTTPS), ARCHITECTURE and (OS) RELEASE
    API_PORT = "443"
    ARCHITECTURE = get_architecture()
    try:
        RELEASE = platform.linux_distribution()[1]
    except AttributeError:
        RELEASE = platform.dist()[1]

    SKIP_STEPS = ['foreman', 'puppet', 'migration', 'prereq-update', 'katello-agent', 'remove-obsolete-packages']

    # > Define and parse the options
    parser = OptionParser()
    parser.add_option("-s", "--server", dest="foreman_fqdn", help="FQDN of Foreman OR Capsule - omit https://", metavar="foreman_fqdn")
    parser.add_option("-l", "--login", dest="login", default='admin', help="Login user for API Calls", metavar="LOGIN")
    parser.add_option("-p", "--password", dest="password", help="Password for specified user. Will prompt if omitted", metavar="PASSWORD")
    parser.add_option("--fqdn", dest="fqdn", help="Set an explicit FQDN, overriding detected FQDN from socket.getfqdn(), currently detected as %default", metavar="FQDN", default=socket.getfqdn())
    parser.add_option("--legacy-login", dest="legacy_login", default='admin', help="Login user for Satellite 5 API Calls", metavar="LOGIN")
    parser.add_option("--legacy-password", dest="legacy_password", help="Password for specified Satellite 5 user. Will prompt if omitted", metavar="PASSWORD")
    parser.add_option("--legacy-purge", dest="legacy_purge", action="store_true", help="Purge system from the Legacy environment (e.g. Sat5)")
    parser.add_option("-a", "--activationkey", dest="activationkey", help="Activation Key to register the system", metavar="ACTIVATIONKEY")
    parser.add_option("-P", "--skip-puppet", dest="no_puppet", action="store_true", default=False, help="Do not install Puppet")
    parser.add_option("--skip-foreman", dest="no_foreman", action="store_true", default=False, help="Do not create a Foreman host. Implies --skip-puppet. When using --skip-foreman, you MUST pass the Organization's LABEL, not NAME")
    parser.add_option("-g", "--hostgroup", dest="hostgroup", help="Title of the Hostgroup in Foreman that the host is to be associated with", metavar="HOSTGROUP")
    parser.add_option("-L", "--location", dest="location", help="Title of the Location in Foreman that the host is to be associated with", metavar="LOCATION")
    parser.add_option("-O", "--operatingsystem", dest="operatingsystem", default=None, help="Title of the Operating System in Foreman that the host is to be associated with", metavar="OPERATINGSYSTEM")
    parser.add_option("--partitiontable", dest="partitiontable", default=None, help="Name of the Partition Table in Foreman that the host is to be associated with", metavar="PARTITIONTABLE")
    parser.add_option("-o", "--organization", dest="org", default='Default Organization', help="Name of the Organization in Foreman that the host is to be associated with", metavar="ORG")
    parser.add_option("-S", "--subscription-manager-args", dest="smargs", default="", help="Which additional arguments shall be passed to subscription-manager", metavar="ARGS")
    parser.add_option("--rhn-migrate-args", dest="rhsmargs", default="", help="Which additional arguments shall be passed to rhn-migrate-classic-to-rhsm", metavar="ARGS")
    parser.add_option("-u", "--update", dest="update", action="store_true", help="Fully Updates the System")
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="Verbose output")
    parser.add_option("-f", "--force", dest="force", action="store_true", help="Force registration (will erase old katello and puppet certs)")
    parser.add_option("--add-domain", dest="add_domain", action="store_true", help="Automatically add the clients domain to Foreman")
    parser.add_option("--remove", dest="remove", action="store_true", help="Instead of registring the machine to Foreman remove it")
    parser.add_option("-r", "--release", dest="release", default=RELEASE, help="Specify release version")
    parser.add_option("-R", "--remove-obsolete-packages", dest="removepkgs", action="store_true", help="Remove old Red Hat Network and RHUI Packages (default)", default=True)
    parser.add_option("--download-method", dest="download_method", default="http", help="Method to download katello-ca-consumer package (e.g. http or https)", metavar="DOWNLOADMETHOD", choices=['http', 'https'])
    parser.add_option("--no-remove-obsolete-packages", dest="removepkgs", action="store_false", help="Don't remove old Red Hat Network and RHUI Packages")
    parser.add_option("--unmanaged", dest="unmanaged", action="store_true", help="Add the server as unmanaged. Useful to skip provisioning dependencies.")
    parser.add_option("--rex", dest="remote_exec", action="store_true", help="Install Foreman's SSH key for remote execution.", default=False)
    parser.add_option("--rex-user", dest="remote_exec_user", default="root", help="Local user used by Foreman's remote execution feature.")
    parser.add_option("--enablerepos", dest="enablerepos", help="Repositories to be enabled via subscription-manager - comma separated", metavar="enablerepos")
    parser.add_option("--skip", dest="skip", action="append", help="Skip the listed steps (choices: %s)" % SKIP_STEPS, choices=SKIP_STEPS, default=[])
    parser.add_option("--ip", dest="ip", help="IPv4 address of the primary interface in Foreman (defaults to the address used to make request to Foreman)")
    (options, args) = parser.parse_args()

    if options.no_foreman:
        options.skip.append('foreman')
    if options.no_puppet:
        options.skip.append('puppet')
    if not options.removepkgs:
        options.skip.append('remove-obsolete-packages')

    # > Validate that the options make sense or exit with a message.
    # the logic is as follows:
    #   if mode = create:
    #     foreman_fqdn
    #     org
    #     activation_key
    #     if foreman:
    #       hostgroup
    #   else if mode = remove:
    #     if removing from foreman:
    #        foreman_fqdn
    if not ((options.remove and ('foreman' in options.skip or options.foreman_fqdn)) or
            (options.foreman_fqdn and options.org and options.activationkey and ('foreman' in options.skip or options.hostgroup))):
        if not options.remove:
            print "Must specify server, login, organization, hostgroup and activation key.  See usage:"
        else:
            print "Must specify server.  See usage:"
        parser.print_help()
        print "\nExample usage: ./bootstrap-wrapper.py -l admin -s foreman.example.com -o 'Default Organization' -L 'Default Location' -g My_Hostgroup -a My_Activation_Key"
        sys.exit(1)

    # > Gather FQDN, HOSTNAME and DOMAIN using options.fqdn
    # > If socket.fqdn() returns an FQDN, derive HOSTNAME & DOMAIN using FQDN
    # > else, HOSTNAME isn't an FQDN
    # > if user passes --fqdn set FQDN, HOSTNAME and DOMAIN to the parameter that is given.
    FQDN = options.fqdn
    if FQDN.find(".") != -1:
        HOSTNAME = FQDN.split('.')[0]
        DOMAIN = FQDN[FQDN.index('.') + 1:]
    else:
        HOSTNAME = FQDN
        DOMAIN = None

    # > Exit if DOMAIN isn't set and Puppet must be installed (without force)
    if not DOMAIN and not (options.force or 'puppet' in options.skip):
        print "We could not determine the domain of this machine, most probably `hostname -f` does not return the FQDN."
        print "This can lead to Puppet missbehaviour and thus the script will terminate now."
        print "You can override this by passing one of the following"
        print "\t--force - to disable all checking"
        print "\t--skip-puppet - to omit installing the puppet agent"
        sys.exit(1)

    # > Gather primary IP address if none was given
    # we do this *after* parsing options to find the IP on the interface
    # towards the Foreman instance in the case the machine has multiple
    if not options.ip:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((options.foreman_fqdn, 80))
            options.ip = s.getsockname()[0]
            s.close()
        except:
            options.ip = None

    # > Ask for the password if not given as option
    #if not options.password and 'foreman' not in options.skip:
    #    options.password = getpass.getpass("%s's password:" % options.login)

    # > If user wants to purge profile from RHN/Satellite 5, credentials are needed.
    if options.legacy_purge and not options.legacy_password:
        options.legacy_password = getpass.getpass("Legacy User %s's password:" % options.legacy_login)

    # > Puppet won't be installed if Foreman Host shall not be created
    if 'foreman' in options.skip:
        options.skip.append('puppet')

    options.skip = set(options.skip)

    # > Output all parameters if verbose.
    if options.verbose:
        print "HOSTNAME - %s" % HOSTNAME
        print "DOMAIN - %s" % DOMAIN
        print "FQDN - %s" % FQDN
        print "RELEASE - %s" % RELEASE
        print "MAC - %s" % MAC
        print "IP - %s" % options.ip
        print "foreman_fqdn - %s" % options.foreman_fqdn
        print "LOGIN - %s" % options.login
        print "PASSWORD - %s" % options.password
        print "HOSTGROUP - %s" % options.hostgroup
        print "LOCATION - %s" % options.location
        print "OPERATINGSYSTEM - %s" % options.operatingsystem
        print "PARTITIONTABLE - %s" % options.partitiontable
        print "ORG - %s" % options.org
        print "ACTIVATIONKEY - %s" % options.activationkey
        print "UPDATE - %s" % options.update
        print "LEGACY LOGIN - %s" % options.legacy_login
        print "LEGACY PASSWORD - %s" % options.legacy_password
        print "DOWNLOAD METHOD - %s" % options.download_method
        print "SKIP - %s" % options.skip

    # > Exit if the user isn't root.
    # Done here to allow an unprivileged user to run the script to see
    # its various options.
    if os.getuid() != 0:
        print_error("This script requires root-level access")
        sys.exit(1)

    # > Try to import json or simplejson.
    # do it at this point in the code to have our custom print and exec
    # functions available
    try:
        import json
    except ImportError:
        try:
            import simplejson as json
        except ImportError:
            print_warning("Could neither import json nor simplejson, will try to install simplejson and re-import")
            yum("install", "python-simplejson")
            try:
                import simplejson as json
            except ImportError:
                print_error("Could not install python-simplejson")
                sys.exit(1)

    # > Clean the environment from LD_... variables
    clean_environment()

    if not options.remove:
        if options.remote_exec:
            install_foreman_ssh_key()

    run_bootstrap()

