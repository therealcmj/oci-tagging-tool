import logging


class ociClient(object):
    clients = {}

    def __init__(self, ottconfig, clientClass ):
        logging.debug("Initializing client class {} for home region {}".format(clientClass, ottconfig._home_region))
        self.clients[ottconfig._home_region] = clientClass(ottconfig.ociconfig)

        for region in ottconfig._regions:
            logging.debug("Initializing client class {} for region {}".format(clientClass,region))

            rconfig = ottconfig.ociconfig
            logging.debug("Old region in this OCI config dict: {}".format(rconfig["region"]))
            rconfig["region"] = region
            logging.debug("New region in this OCI config dict: {}".format(rconfig["region"]))

            self.clients[region] = clientClass(rconfig)
