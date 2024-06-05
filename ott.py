#!/usr/bin/env python3

import json
import logging

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(threadName)s %(levelname)7s %(module)s:%(funcName)s -> %(message)s',
                        level=logging.INFO)

    logging.info("Parsing command line and configuring...")
    from ott.config import config

    cfg = config()
    logging.debug("Configured")

    logging.debug("Preparing for search")
    from ott.search import search

    srch = search(cfg)

    # at this point we have the search results
    results = srch.find_resource(cfg._search_string)

    if not results:
        logging.error("No results returned from search.")
    else:
        for region in results:
            logging.info("Region {}".format(region))

            from ott.tagger import tagger
            t = tagger(cfg)

            for item in results[region]:
                # I feel like this should be in tagger. But am not convinced
                logging.debug("Item info:")
                logging.debug("          ID: {}".format(item.identifier))
                logging.debug(" Compartment: {}".format(item.compartment_id))
                logging.debug("        Type: {}".format(item.resource_type))

                # check out my tricky trick...
                item.region = region

                t.queueUpdate( item, cfg._change )

            if cfg._dryRun:
                logging.info("Dry run. Changes not being made")
            else:
                t.executeUpdate(cfg._change)
