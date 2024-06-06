import logging
import oci

from ott.ociClient import ociClient

class tagger(ociClient):
    _resourcetypes = []

    _tochange = {}

    # _tochange is going to be
    # {
    #     region1 : {
    #         compartment1 : [
    #           "ocid1.xxx",
    #           "ocid1.xxx"
    #         ],
    #         compartment2 : []
    #         ...
    #     },
    #     region2 : {
    #         compartment1 : [],
    #         compartment3 : []
    #         ...
    #     },
    #     ...
    # }
    #
    # !!!!!!!!!!!!!!!!
    # !!! HOWEVER !!!!
    # !!!!!!!!!!!!!!!!
    #
    # the code I'm writing in ott.py will execute the queued changes region by region

    def __init__(self, ottconfig):
        super().__init__(ottconfig, oci.identity.IdentityClient)

        # get a list of the supported resources
        result = oci.pagination.list_call_get_all_results(
            self.clients[ottconfig._home_region].list_bulk_edit_tags_resource_types,
            *[],
            **{}
        ).data

        for type in result:
            resourcetype = type.resource_type
            logging.debug("Supported Resource type: {}".format(resourcetype))
            self._resourcetypes.append(resourcetype)
        logging.info("{} resources types supported by Bulk Tag APIs".format(len(self._resourcetypes)))

    def getTagValue(self, item, tag):
        if "." in tag:
            (namespace,name) = tag.split(".")

            if namespace in item.defined_tags and name in item.defined_tags[namespace]:
                return item.defined_tags[namespace][name]
            else:
                return None
        else:
            if tag in item.freeform_tags:
                return item.freeform_tags[tag]
            else:
                return None

    def needToApplyChange(self, item, change):
        # this feels kinda messy but it's pretty clear

        value = self.getTagValue(item, change.tag())

        if change.isDelete():
            # I could do this all on one line but this is more readable
            if None == value:
                return False
            else:
                return True

        # implied else
        if value == change.tagValue():
            return False
        else:
            return True

    def queueUpdate(self, item, change ):

        if not self.needToApplyChange(item, change):
            logging.debug("No need to apply change to this object")
            return
        else:
            logging.debug("Need to apply change")

            if item.resource_type in self._resourcetypes:
                logging.debug("Resource type IS supported by Bulk Tag API")

                # allocate the array of changes for the region
                if not item.region in self._tochange:
                    self._tochange[item.region] = {}

                if not item.compartment_id in self._tochange[item.region]:
                    self._tochange[item.region][item.compartment_id] = []

                self._tochange[item.region][item.compartment_id].append(
                    oci.identity.models.BulkEditResource(
                        id = item.identifier,
                        resource_type = item.resource_type
                    ))

            else:
                logging.error("Resource {} of type {} is NOT supported by bulk tagging API".format(item.identifier, item.resource_type))

    def executeUpdate(self, change):

        # build the actual change
        beod = None

        if change.isDelete():
            # untested!
            if change.isDefined():
                raise Exception("Not implemented yet")

        else:
            if change.isDefined():
                beod = oci.identity.models.BulkEditOperationDetails(
                    operation_type="ADD_OR_SET",
                    defined_tags={
                        change.tagNamespace(): {
                            change.tagName(): change.tagValue()
                        }
                    }
                )
            else:
                beod = oci.identity.models.BulkEditOperationDetails(
                    operation_type="ADD_OR_SET",
                    freeform_tags={
                        change.tagName(): change.tagValue()
                    }
                )

        for region in self._tochange:
            for compartment in self._tochange[region]:
                logging.info("Prepping {} changes for compartment {} in region {}".format(len(self._tochange[region][compartment]),compartment,region))

                # the bulk tag API only allows 100 at a time
                step = 100
                for i in range(0, len(self._tochange[region][compartment]), step):
                    x = i
                    logging.info("Updating resources {} through (up to) {}".format(x,x+step))
                    bed = oci.identity.models.BulkEditTagsDetails(
                        compartment_id=compartment,
                        resources=self._tochange[region][compartment][x:x + step],
                        bulk_edit_operations=[beod]
                    )

                    custom_retry_strategy = oci.retry.RetryStrategyBuilder(
                        # Make up to 10 service calls
                        max_attempts_check=True,
                        max_attempts=100,

                        # Don't exceed a total of 600 seconds for all service calls
                        total_elapsed_time_check=True,
                        total_elapsed_time_seconds=600,

                        # Wait 45 seconds between attempts
                        retry_max_wait_between_calls_seconds=45,

                        # Use 2 seconds as the base number for doing sleep time calculations
                        retry_base_sleep_time_seconds=2,

                        # Retry on certain service errors:
                        #
                        #   - 5xx code received for the request
                        #   - Any 429 (this is signified by the empty array in the retry config)
                        #   - 400s where the code is QuotaExceeded or LimitExceeded
                        service_error_check=True,
                        service_error_retry_on_any_5xx=True,
                        service_error_retry_config={
                            400: ['QuotaExceeded', 'LimitExceeded'],
                            429: []
                        },

                        # Use exponential backoff and retry with full jitter, but on throttles use
                        # exponential backoff and retry with equal jitter
                        backoff_type=oci.retry.BACKOFF_FULL_JITTER_EQUAL_ON_THROTTLE_VALUE
                    ).get_retry_strategy()

                    logging.debug("Sending request")
                    response = self.clients[region].bulk_edit_tags( bulk_edit_tags_details=bed, retry_strategy=custom_retry_strategy )
                    logging.debug("Response")
                    logging.debug(response.headers)

                    logging.info("Work request ID {}".format(response.headers["opc-work-request-id"]))

                # these three lines clean up as we go
                self._tochange[region][compartment] = []
            self._tochange[region] = {}
        self._tochange = {}

