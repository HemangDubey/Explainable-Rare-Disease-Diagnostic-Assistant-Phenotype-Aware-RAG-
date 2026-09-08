"""Client for querying NCBI E-Utilities (ESearch, ESummary, EFetch) with real PubMed data."""

import os
import time
import urllib.request
import urllib.parse
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
import logging

from src.literature.schemas import PubMedArticle, EvidenceCategory, EvidenceStrength
from src.literature.cache import LiteratureCache

logger = logging.getLogger(__name__)


class PubMedClient:
    """Communicates directly with official NCBI Entrez E-Utilities endpoints."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, cache_dir: str = "data/cache/pubmed", email: Optional[str] = None):
        self.cache = LiteratureCache(cache_dir=cache_dir)
        self.email = email or os.environ.get("NCBI_EMAIL", "rare_disease_assistant@clinical.ai")
        self.api_key = os.environ.get("NCBI_API_KEY", None)
        self.last_request_time = 0.0
        # NCBI rate limits: max 3 requests/second without key, 10 with key
        self.min_interval = 0.35 if not self.api_key else 0.12

    def _rate_limit(self):
        """Enforces NCBI request pacing."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def _http_get(self, url: str) -> Optional[bytes]:
        """Makes a GET request with standard headers and timeout."""
        self._rate_limit()
        headers = {
            "User-Agent": f"ExplainableRareDiseaseAssistant/1.0 ({self.email})"
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return response.read()
        except Exception as e:
            logger.warning(f"NCBI request failed for {url}: {e}")
            return None

    def search_pmids(self, query: str, max_results: int = 10) -> List[str]:
        """Searches PubMed via esearch.fcgi and returns matching PMIDs."""
        # 1. Check local query cache first
        cached_pmids = self.cache.get_query_results(query)
        if cached_pmids is not None:
            return cached_pmids[:max_results]

        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": str(max_results),
            "sort": "relevance",
            "email": self.email
        }
        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.BASE_URL}/esearch.fcgi?{urllib.parse.urlencode(params)}"
        raw_data = self._http_get(url)
        if not raw_data:
            return []

        try:
            res_json = json.loads(raw_data.decode("utf-8"))
            id_list = res_json.get("esearchresult", {}).get("idlist", [])
            self.cache.set_query_results(query, id_list)
            return id_list
        except Exception as e:
            logger.error(f"Error parsing esearch response: {e}")
            return []

    def fetch_articles_by_pmids(self, pmids: List[str]) -> List[PubMedArticle]:
        """Fetches metadata and abstracts for given PMIDs using efetch and esummary."""
        if not pmids:
            return []

        articles: List[PubMedArticle] = []
        to_fetch: List[str] = []

        # Check local cache first for each article
        for pmid in pmids:
            cached_data = self.cache.get_article(pmid)
            if cached_data:
                try:
                    articles.append(PubMedArticle(**cached_data))
                except Exception:
                    to_fetch.append(pmid)
            else:
                to_fetch.append(pmid)

        if not to_fetch:
            return articles

        # Batch fetch via efetch.fcgi in XML format to retrieve full abstracts
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(to_fetch),
            "retmode": "xml",
            "email": self.email
        }
        if self.api_key:
            fetch_params["api_key"] = self.api_key

        fetch_url = f"{self.BASE_URL}/efetch.fcgi?{urllib.parse.urlencode(fetch_params)}"
        raw_xml = self._http_get(fetch_url)
        if not raw_xml:
            # Fallback to esummary if efetch fails
            return articles + self._fetch_summaries_fallback(to_fetch)

        try:
            root = ET.fromstring(raw_xml)
            for article_elem in root.findall(".//PubmedArticle"):
                parsed = self._parse_pubmed_xml_article(article_elem)
                if parsed:
                    self.cache.set_article(parsed.pmid, parsed.dict())
                    articles.append(parsed)
        except Exception as e:
            logger.error(f"XML parsing error in efetch: {e}")
            fallback_articles = self._fetch_summaries_fallback(to_fetch)
            articles.extend(fallback_articles)

        return articles

    def _fetch_summaries_fallback(self, pmids: List[str]) -> List[PubMedArticle]:
        """Fallback retrieving minimal metadata from esummary.fcgi JSON."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
            "email": self.email
        }
        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.BASE_URL}/esummary.fcgi?{urllib.parse.urlencode(params)}"
        raw_data = self._http_get(url)
        if not raw_data:
            return []

        out = []
        try:
            data = json.loads(raw_data.decode("utf-8"))
            result_dict = data.get("result", {})
            for pmid in pmids:
                if pmid in result_dict and pmid != "uids":
                    item = result_dict[pmid]
                    title = item.get("title", "")
                    journal = item.get("source", "")
                    pubdate = item.get("pubdate", "")
                    pub_year = pubdate.split()[0] if pubdate else None
                    authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
                    doi = None
                    for article_id in item.get("articleids", []):
                        if article_id.get("idtype") == "doi":
                            doi = article_id.get("value")

                    art = PubMedArticle(
                        pmid=pmid,
                        title=title,
                        abstract="",
                        journal=journal,
                        pub_year=pub_year,
                        authors=authors,
                        doi=doi,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    )
                    self.cache.set_article(pmid, art.dict())
                    out.append(art)
        except Exception as e:
            logger.error(f"Error in esummary fallback: {e}")
        return out

    def _parse_pubmed_xml_article(self, elem: ET.Element) -> Optional[PubMedArticle]:
        """Parses a single PubmedArticle XML element."""
        try:
            pmid_elem = elem.find(".//MedlineCitation/PMID")
            if pmid_elem is None or not pmid_elem.text:
                return None
            pmid = pmid_elem.text.strip()

            title_elem = elem.find(".//ArticleTitle")
            title = "".join(title_elem.itertext()).strip() if title_elem is not None else "No Title"

            # Parse abstract
            abstract_parts = []
            for abs_elem in elem.findall(".//AbstractText"):
                part_text = "".join(abs_elem.itertext()).strip()
                label = abs_elem.attrib.get("Label")
                if label:
                    abstract_parts.append(f"{label}: {part_text}")
                else:
                    abstract_parts.append(part_text)
            abstract = "\n\n".join(abstract_parts)

            journal_elem = elem.find(".//Journal/Title")
            journal = journal_elem.text.strip() if journal_elem is not None and journal_elem.text else ""

            # Year
            year_elem = elem.find(".//JournalIssue/PubDate/Year")
            if year_elem is None:
                year_elem = elem.find(".//DateCompleted/Year")
            pub_year = year_elem.text.strip() if year_elem is not None and year_elem.text else None

            # Authors
            authors = []
            for author_elem in elem.findall(".//AuthorList/Author"):
                last_name = author_elem.find("LastName")
                fore_name = author_elem.find("ForeName")
                if last_name is not None and last_name.text:
                    if fore_name is not None and fore_name.text:
                        authors.append(f"{last_name.text} {fore_name.text}")
                    else:
                        authors.append(last_name.text)

            # DOI
            doi = None
            for id_elem in elem.findall(".//ArticleIdList/ArticleId"):
                if id_elem.attrib.get("IdType") == "doi" and id_elem.text:
                    doi = id_elem.text.strip()

            return PubMedArticle(
                pmid=pmid,
                title=title,
                abstract=abstract,
                journal=journal,
                pub_year=pub_year,
                authors=authors,
                doi=doi,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            )
        except Exception as e:
            logger.warning(f"Error parsing single XML article: {e}")
            return None
