import json
from typing import Tuple

from assemblyline.common.str_utils import safe_str
from assemblyline_v4_service.common.base import ServiceBase
from assemblyline_v4_service.common.request import ServiceRequest
from assemblyline_v4_service.common.result import Result, ResultSection, BODY_FORMAT
from assemblyline_v4_service.common.task import MaxExtractedExceeded

from dexray.dexray_lib import extract_ahnlab, extract_avast_avg, extract_mcafee_bup, \
    extract_defender, extract_trendmicro


class Dexray(ServiceBase):
    def __init__(self, config=None):
        super(Dexray, self).__init__(config)
        self.extract_methods = [
            extract_ahnlab,
            extract_avast_avg,
            extract_mcafee_bup,
            extract_defender,
            extract_trendmicro
        ]
        self.sha = None

    def start(self):
        self.log.info(f"start() from {self.service_attributes.name} service called")

    def execute(self, request: ServiceRequest):
        """Main Module. See README for details."""
        result = Result()
        self.sha = request.sha256
        local = request.file_path

        extracted, metadata = self.dexray(request, local)

        num_extracted = len(request.extracted)
        if num_extracted != 0:
            text_section = ResultSection("DeXRAY found files:")
            for extracted in request.extracted:
                file_name = extracted.get("name")
                text_section.add_line(f"Resubmitted un-quarantined file as : {file_name}")
            result.add_section(text_section)

        if metadata:
            # Can contain live URLs to the original content source
            kv_section = ResultSection("DeXRAY Quarantine Metadata",
                                       body_format=BODY_FORMAT.JSON,
                                       body=json.dumps(metadata))
            result.add_section(kv_section)

        request.result = result

    def dexray(self, request: ServiceRequest, local: str) -> Tuple[list, dict]:
        """Iterate through quarantine decrypt methods.
        Args:
            request: AL request object.
            local: File path of AL sample.
        Returns:
            True if archive is password protected, and number of white-listed embedded files.
        """
        encoding = request.file_type.replace("quarantine/", "")
        extracted = []
        metadata = {}

        # Try all extracting methods
        for extract_method in self.extract_methods:
            # noinspection PyArgumentList
            self.log.debug("Attempting extract with %s" % extract_method.__name__)
            extracted, metadata = extract_method(local, self.sha, self.working_directory, encoding)
            if extracted or metadata:
                self.log.info("Successfully extracted file or metadata with %s" % extract_method.__name__)
                break

        extracted_count = len(extracted)
        # safe_str the file name (fn)
        extracted = [[fp, safe_str(fn), e] for fp, fn, e in extracted]
        for child in extracted:
            try:
                # If the file is not successfully added as extracted, then decrease the extracted file counter
                if not request.add_extracted(*child):
                    extracted_count -= 1
            except MaxExtractedExceeded:
                raise MaxExtractedExceeded(f"This file contains {extracted_count} extracted files, exceeding the "
                                           f"maximum of {request.max_extracted} extracted files allowed. "
                                           "None of the files were extracted.")

        return extracted, metadata
