import logging


class ociClient(object):
    clients = {}
    compositeClients = {}
    home_region = None

    _ottconfig = None
    _client_class = None
    _composite_client_class = None

    def __init__(self, ottconfig, clientClass, clientCompositeClass=None ):
        self.clients = {}
        self.compositeClients = {}

        self._ottconfig = ottconfig

        self.home_region = ottconfig._home_region

        self._client_class = clientClass
        self._composite_client_class = clientCompositeClass

        logging.debug("Initializing client class {} for home region {}".format(clientClass, ottconfig._home_region))
        self.clients[ottconfig._home_region] = clientClass(ottconfig.ociconfig)
        if clientCompositeClass:
            self.compositeClients[ottconfig._home_region] = clientCompositeClass(ottconfig.ociconfig)

        logging.debug("Done initializing (clients for other regions will be lazy initialized only when needed)")

    def get_client(self, region):
        logging.debug("Getting client for {}".format(region))

        if not region in self.clients:
            logging.debug("Initializing client class {} for region {}".format(self._client_class,region))

            rconfig = dict(self._ottconfig.ociconfig)
            logging.debug("Old region in this OCI config dict: {}".format(rconfig["region"]))
            rconfig["region"] = region
            logging.debug("New region in this OCI config dict: {}".format(rconfig["region"]))

            self.clients[region] = self._client_class(rconfig)
            logging.debug("Initialized.")

        return self.clients[region]
    
    def get_composite_client(self, region):
        logging.debug("Getting composite client for {}".format(region))

        if not region in self.compositeClients:
            logging.debug("Initializing composite client class {} for region {}".format(self._composite_client_class,region))

            rconfig = dict(self._ottconfig.ociconfig)
            logging.debug("Old region in this OCI config dict: {}".format(rconfig["region"]))
            rconfig["region"] = region
            logging.debug("New region in this OCI config dict: {}".format(rconfig["region"]))

            self.clients[region] = self._composite_client_class(rconfig)
            logging.debug("Initialized.")

        return self.compositeClients[region]
