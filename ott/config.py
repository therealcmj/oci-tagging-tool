
# shamelessly stolen from myself / ociextirpater

class config:

    class change():
        _changetype         = None
        _isDefined          = False
        _tag                = None   # keep the provided (un processed) tag if provided. For reasons...
        _tagNamespace       = None
        _tagName            = None
        _value              = None

        def __init__(self, changetype, tag, value = None):
            if changetype == "delete":
                # then the tag value had better be empty
                if value:
                    raise Exception("Do not specify value when deleting tags")

            # changetype is either set or delete
            self._changetype = changetype

            self._tag = tag

            # defined tags always have a namespace + dot + name
            self._isDefined = "." in tag
            if self._isDefined:
                (self._tagNamespace, self._tagName) = tag.split(".")
            else:
                self._tagName = tag

            self._tagValue = value

        def isDelete(self):
            return self._changetype == "delete"

        def isDefined(self):
            return self._isDefined

        def tagNamespace(self):
            return self._tagNamespace

        def tag(self):
            return self._tag

        def tagName(self):
            return self._tagName

        def tagValue(self):
            return self._tagValue

    signer = None
    ociconfig = None

    #TODO: generate accessors
    _home_region = None
    _regions = []

    _dryRun = True

    _search_string = None
    _change = None

    def __init__(self):
        import logging, logging.handlers
        import argparse

        # parser = argparse.ArgumentParser(formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=80, width=130))
        parser = argparse.ArgumentParser(
            prog="ott",
            description="The OCI Tagging Tool",
            epilog="Written by Chris Johnson"
                    " | "
                   "https://www.github.com/therealcmj"
                    " | "
                   "https://blogs.oracle.com/authors/christopher-johnson"
        )

        # I'm going to use most of the same arguments as OCI SuperDelete / OCI Extirpater
        parser.add_argument('-cf', default="~/.oci/config", dest='config_file', help='OCI Config file')
        parser.add_argument('-cp', default="DEFAULT", dest='config_profile', help='Config Profile inside the config file')

        parser.add_argument('-l', '-log', dest='log_file', type=argparse.FileType('w'), help='output log file')
        parser.add_argument('-d', '-debug', dest='debug', default=False, action='store_true', help='Enable debug')
        parser.add_argument('-n', "--dry-run", dest='dryrun', default=False, action='store_true', help="Dry run - do not actually make the specified changes")

        parser.add_argument('-rg','--region', dest='regions', help="Comma list of regions separated (defaults to all subscribed regions)")

        # then positional arguments:
        parser.add_argument('query')
        parser.add_argument('action', choices=["set","delete"])  # NOTE: this is different from the bulk API. I'm simplifying

        # I was going to make you specify ff or d, but if the tag contains a . then it's a defined tag. If not it's a freform tag
        # parser.add_argument('TagNameSpace', choices=["d","defined","ff","freeform"])
        parser.add_argument('tag')
        parser.add_argument('value', default="")

        cmd = parser.parse_args()

        # process the logging arguments first
        rootLogger = logging.getLogger()
        #
        if cmd.log_file:
            rootLogger.addHandler( logging.handlers.WatchedFileHandler(cmd.log_file) )
            logging.info("Logging to log file '{}'".format( cmd.log_file))
        #
        if cmd.debug:
            rootLogger.setLevel("DEBUG")
            logging.debug("Log level set to DEBUG")

        if cmd.dryrun:
            logging.info("Dry Run is set - changes will not be made")
            self._dryRun = True
        else:
            logging.info("Dry Run is NOT set - changes WILL be made")
            self._dryRun = False


        # then process the other arguments
        import oci

        logging.info("Preparing signer")
        # we construct the right signer here
        # if cmd.is_instance_principal:
        #     logging.debug("Authenticating with Instance Principal")
        #     try:
        #         signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        #         self.ociconfig = {
        #             'region': signer.region,
        #             'tenancy': signer.tenancy_id
        #         }
        #
        #     except Exception:
        #         errTxt = "Error obtaining instance principals certificate, aborting"
        #         logging.error(errTxt)
        #         raise Exception(errTxt)
        #
        # elif cmd.is_delegation_token:
        #     logging.debug("Authenticating with Delegation Token")
        #
        #     self.ociconfig = oci.config.from_file(cmd.config_file, cmd.config_profile)
        #     delegation_token_location = self.ociconfig["delegation_token_file"]
        #
        #     with open(delegation_token_location, 'r') as delegation_token_file:
        #         delegation_token = delegation_token_file.read().strip()
        #         # get signer from delegation token
        #         self.signer = oci.auth.signers.InstancePrincipalsDelegationTokenSigner(delegation_token=delegation_token)
        #
        # # otherwise use the config file yada yada
        # else:
        if True:
            try:
                self.ociconfig = oci.config.from_file( cmd.config_file,cmd.config_profile )
                self.signer = oci.signer.Signer.from_config(self.ociconfig)
            except:
                errTxt = "Error obtaining authentication, did you configure config file? aborting"
                logging.error(errTxt)
                raise Exception(errTxt)

        logging.info("Signer prepared")

        self.identity_client = oci.identity.IdentityClient(self.ociconfig, signer=self.signer)

        # regions
        requested_regions = None
        if cmd.regions:
            logging.debug("Regions specified on command line")
            # TODO: make sure that the user doesn't request a region that they aren't subscribed to
            # requested_regions = cmd.regions.split(",")
            self._regions = cmd.regions.split(",")
        else:
            logging.debug("Regions not specified on command line.")

        logging.info( "{} Regions to be operated upon: {}".format(len(self._regions), self._regions))

        logging.info("Getting subscribed regions...")
        regions = self.identity_client.list_region_subscriptions(self.ociconfig["tenancy"]).data
        for region in regions:
            if region.is_home_region:
                self._home_region = region.region_name

        logging.info( "Home region: {}".format(self._home_region))

        self._search_string = cmd.query
        self._action = cmd.action

        self._change = self.change( self._action, cmd.tag, cmd.value)
