import logging
import oci
import json

from ott.ociClient import ociClient

class tagger(ociClient):
    _resourcetypes = []

    _tochange = {}
    _workRequests = {}

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
        super().__init__(ottconfig, oci.identity.IdentityClient, oci.identity.IdentityClientCompositeOperations)

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
                logging.debug("There are now {} items to change in compartment {} in region {}".format(len(self._tochange[item.region][item.compartment_id]), item.compartment_id, item.region))

            else:
                logging.error("Resource {} of type {} is NOT supported by bulk tagging API".format(item.identifier, item.resource_type))

    def executeUpdate(self, change, wait):

        # build the actual change
        beod = None

        if change.isDelete():
            if change.isDefined():
                beod = oci.identity.models.BulkEditOperationDetails(
                    operation_type="REMOVE",
                    defined_tags={
                        change.tagNamespace(): {
                            change.tagName(): ""
                        }
                    }
                )
            else:
                beod = oci.identity.models.BulkEditOperationDetails(
                    operation_type="REMOVE",
                    freeform_tags={
                        change.tagName(): ""
                    }
                )

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
                    # logging.debug("Request: {}".format(json.dumps(bed)))

                    response = self.clients[region].bulk_edit_tags( bulk_edit_tags_details=bed, retry_strategy=custom_retry_strategy )
                    logging.debug("Response")
                    logging.debug(response.headers)

                    wrid = response.headers["opc-work-request-id"]
                    if not region in self._workRequests:
                        self._workRequests[region] = []
                    self._workRequests[region].append(wrid)

                    logging.info("Work request ID {}".format(wrid))

                # these three lines clean up as we go
                self._tochange[region][compartment] = []
            self._tochange[region] = {}
        self._tochange = {}


        if wait:
            # at this point _workRequests is something like
            # {
            #   "us-ashburn-1": [ "ocid1.taggingworkrequest.oc1..a", "ocid1.taggingworkrequest.oc1..b"...]
            #   "us-phoenix-1": [ "ocid1.taggingworkrequest.oc1..a" ]
            # }
            #
            # with any(?) luck a bunch of those will be done already

            while len(self._workRequests) > 0:
                for region in self._workRequests:
                    logging.debug("Waiting for {} Work Requests in region {} to finish".format(len(self._workRequests[region]),region))
                    for wrid in self._workRequests[region]:
                        result = self.clients[region].get_tagging_work_request(wrid)

                        # We consider "SUCCEEDED", PARTIALLY_SUCCEEDED, CANCELLED, an FAILED as done
                        # which leaves ACCEPTED, IN_PROGRESS, or CANCELLING as "still going"
                        # I feel like there ought to be a utlity function for this. TODO: look for one
                        # my left arm for a switch / case
                        logging.info("Work request ID {} is in state {}".format(wrid,result.data.status))
                        if result.data.status == "ACCEPTED" or result.data.status == "IN_PROGRESS":
                            logging.debug("Still running")

                        # slightly wasteful
                        elif result.data.status == "SUCCEEDED" or result.data.status == "PARTIALLY_SUCCEEDED" or result.data.status == "CANCELLED" or result.data.status == "FAILED":
                            logging.info("Work request {} complete - state is {}".format(wrid,result.data.status))
                            self._workRequests[region].remove(wrid)

                        else:
                            logging.error("UNKNOWN STATE FOR WORK REQUEST!")
                            logging.error("Please open a bug and report WR state ID {}".format(result.data.status))
                            logging.error("In order to avoid infinite loop I am considering that request complete. BUT THIS IS A BUG!")
                            self._workRequests[region].remove(wrid)

                    # you can't do this because you're not allowed to change the dict during an iteration
                    # if 0 == len( self._workRequests[region]):
                    #     del self._workRequests[region]
                # so make a copy of it and then only copy over the entries that have something in them still
                # I'm sure there's a better way, but it's 9:30 at night and I'm tired
                # TODO: think about this some more
                copy = self._workRequests
                self._workRequests = {}
                for region in copy:
                    if len( copy[region]) > 0:
                        self._workRequests[region] = copy[region]

