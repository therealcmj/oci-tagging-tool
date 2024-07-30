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

            # this code now gets every page of the search results.
            # unfortunately there's no callback for it to notify the caller of progress it's making
            # TODO: look into oci.pagination.list_call_get_all_results_generator() instead.
            #       though that will require a bit of rework of the calling code
            response = oci.pagination.list_call_get_all_results(
                sc.search_resources,
                search_details=oci.resource_search.models.StructuredSearchDetails(type="Structured", query=query)
            )
            logging.info( "Response contains {} item(s) in region {}".format( len(response.data),region ) )
            self.items[region] = response.data

        return self.items

