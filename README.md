# katello-client-bootstrap-wrapper
A Python wrapper script for katello-client-bootstrap which enables argument manipulation and pre- and post- bootstrap tasks to be run

## Origin
This script was written in an afternoon to resolve an issue faced by a client using Red Hat Satellite 6. The requirement was to be extend the functionality of the original **bootstrap.py** script found here:

<https://github.com/Katello/katello-client-bootstrap>

This was to be achieved without modifying the original script as future updates would overwrite their changes, and equally they did not want to have to manage a separate code base and merge their own functionality back into new releases of **bootstrap.py**. In time ideally the features in this wrapper would be contributed (if appropriate) to the original project, but a short term tactical solution was needed. Hopefully this will help someone else out!

## Operation
The script performs the following functions:

1. Performs some basic sanity checks on the arguments passed

2. Assuming we are not in “remove” mode, it intercepts the “--rex” and “--rex-user” flags and uses these to create the user account if it doesn’t already exist. If it exists, it just proceeds with an informational message. If it doesn’t it runs useradd - exception handling is enabled on this command so if the useradd fails, it will exit with an error.

3. Once the user account is created, it proceeds to download the original bootstrap script - it intercepts the value passed to the “-s” flag and uses this to download bootstrap.py from and saves it to the local disk. Again exception handling is enabled so a failed download should result in the script exiting with an appropriate error.

4. Assuming all has gone well, the script then performs some basic processing to build a command array to run the newly downloaded bootstrap.py with the original command line arguments that were passed to the wrapper script.

