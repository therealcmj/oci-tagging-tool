import oci.resource_search.resource_search_client
import logging

from ott.ociClient import ociClient


class search(ociClient):
    items = {}

    def __init__(self, ottconfig):
        super().__init__( ottconfig, oci.resource_search.ResourceSearchClient,oci.resource_search.ResourceSearchClientCompositeOperations)
        return

    def find_resource(self, query):
        logging.info( "Searching with query: {}".format(query))
        # we're going to return **ALL** of the matching resources

        for region in self.clients:
            logging.debug("Preparing to execute query with regional search client for region {}".format(region))
            sc = self.clients[region]

            # TODO: remember to add paging support
            response = sc.search_resources( search_details=oci.resource_search.models.StructuredSearchDetails(type="Structured", query=query))

            logging.info( "Response contains {} item(s) in region {}".format( len(response.data.items),region ) )
            self.items[region] = response.data.items

        # TODO: what should we return here?
        return self.items

