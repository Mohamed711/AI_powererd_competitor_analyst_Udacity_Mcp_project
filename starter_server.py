
import os
import json
import logging
from typing import List, Dict, Optional
from firecrawl import FirecrawlApp
from urllib.parse import urlparse
from datetime import datetime
from mcp.server.fastmcp import FastMCP

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCRAPE_DIR = "scraped_content"

mcp = FastMCP("llm_inference")

@mcp.tool()
def scrape_websites(
    websites: Dict[str, str],
    formats: List[str] = ['markdown', 'html'],
    api_key: Optional[str] = None
) -> List[str]:
    """
    Scrape multiple websites using Firecrawl and store their content.

    Args:
        websites: Dictionary of provider_name -> URL mappings
        formats: List of formats to scrape ['markdown', 'html'] (default: both)
        api_key: Firecrawl API key (if None, expects environment variable)

    Returns:
        List of provider names for successfully scraped websites
    """

    if api_key is None:
        api_key = os.getenv('FIRECRAWL_API_KEY')
        if not api_key:
            raise ValueError("API key must be provided or set as FIRECRAWL_API_KEY environment variable")

    app = FirecrawlApp(api_key=api_key)

    path = os.path.join(SCRAPE_DIR)
    os.makedirs(path, exist_ok=True)

    # save the scraped content to files and then create scraped_metadata.json as a summary file
    # check if the provider has already been scraped and decide if you want to overwrite
    # {
    #     "cloudrift_ai": {
    #         "provider_name": "cloudrift_ai",
    #         "url": "https://www.cloudrift.ai/inference",
    #         "domain": "www.cloudrift.ai",
    #         "scraped_at": "2025-10-23T00:44:59.902569",
    #         "formats": [
    #             "markdown",
    #             "html"
    #         ],
    #         "success": "true",
    #         "content_files": {
    #             "markdown": "cloudrift_ai_markdown.txt",
    #             "html": "cloudrift_ai_html.txt"
    #         },
    #         "title": "AI Inference",
    #         "description": "Scraped content goes here"
    #     }
    # }
    metadata_file = os.path.join(path, "scraped_metadata.json")

    # Read the scrapped metadata if it exists
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r', encoding='utf-8') as f:
            scraped_metadata = json.load(f)
    else:
        scraped_metadata = {}

    successful_scrapes = []

    # Scrap the provided websites
    for provider_name, url in websites.items():
        logger.info(f"Scraping {provider_name} at {url}")

        try:
            scrape_result = app.scrape(url=url, formats=formats).model_dump()

            # Raise an exception if the scrape was not successful
            if scrape_result.get("metadata", {}).get("status_code", 0) != 200:
                raise ValueError(f"Scrape failed for {provider_name} at {url} \
                                  with error: {scrape_result.get("data", {}).get("metadata", {}).get('error', 'Unknown error')}")

            # Read the result data
            scrape_result_data = scrape_result.get("metadata", {})

            content_files = {}
            for fmt in formats:
                content = scrape_result.get(fmt, None)
                if content:
                    filename = f"{provider_name}_{fmt}.txt"
                    filepath = os.path.join(path, filename)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    content_files[fmt] = filename

            scraped_metadata[provider_name] = {
                "provider_name": provider_name,
                "url": url,
                "domain": urlparse(url).netloc,
                "scraped_at": datetime.utcnow().isoformat(),
                "formats": formats,
                "success": True,
                "content_files": content_files,
                "title": scrape_result_data.get("metadata", {}).get("title", ""),
                "description": scrape_result_data.get("metadata", {}).get("description", "")
            }

            successful_scrapes.append(provider_name)
            logger.info(f"Successfully scraped {provider_name}")

        except Exception as e:
            logger.error(f"Failed to scrape {provider_name} at {url}: {e}")
            scraped_metadata[provider_name] = {
                "provider_name": provider_name,
                "url": url,
                "domain": urlparse(url).netloc,
                "scraped_at": datetime.utcnow().isoformat(),
                "formats": formats,
                "success": False,
                "error": str(e)
            }


    # Write the updated metadata back to the file
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(scraped_metadata, f, indent=4)

    logger.info(f"Scraping completed. Successful scrapes: {successful_scrapes}")
    return successful_scrapes

@mcp.tool()
def extract_scraped_info(identifier: str) -> str:
    """
    Extract information about a scraped website.

    Args:
        identifier: The provider name, full URL, or domain to look for

    Returns:
        Formatted JSON string with the scraped information
    """

    logger.info(f"Extracting information for identifier: {identifier}")
    logger.info(f"Files in {SCRAPE_DIR}: {os.listdir(SCRAPE_DIR)}")

    metadata_file = os.path.join(SCRAPE_DIR, "scraped_metadata.json")
    logger.info(f"Checking metadata file: {metadata_file}")

    # The result dictionary
    result = {}

    # Read the scrapped metadata
    if not os.path.exists(metadata_file):
        raise FileNotFoundError(f"Metadata file not found at {metadata_file}")

    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            scraped_metadata = json.load(f)
    except Exception as e:
        raise ValueError(f"Error decoding JSON from metadata file: {e}")

    # Find the matching entry
    matched_entry = None
    for provider_name, data in scraped_metadata.items():
        if identifier == provider_name or identifier == data.get("url") or identifier == data.get("domain"):
            matched_entry = data.copy()
            break

    if matched_entry is None:
        return f"There's no saved information related to identifier '{identifier}'."

    if matched_entry.get("content_files"):
        result["content"] = dict()

        for fmt, filename in matched_entry["content_files"].items():
            filepath = os.path.join(SCRAPE_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                result["content"][fmt] = content
            except Exception as e:
                logger.error(f"Error reading content file {filepath}: {e}")
                return f"There's no saved information related to identifier '{identifier}'."

    return json.dumps(result, indent=2)


if __name__ == "__main__":
    # result = mcp.call_tool(name="scrape_websites", arguments={"websites":{"claudrift":"https://www.cloudrift.ai/inference"}})
    mcp.run(transport="stdio")

    # For testing: uncomment the lines below and comment out mcp.run() above
    # result_ = scrape_websites(
    #     websites={"cloudrift": "https://www.cloudrift.ai/inference"},
    #     formats=['markdown', 'html']
    # )
    # print(f"Scrape result: {result_}")
    #
    # info = extract_scraped_info("cloudrift")
    # print(f"Extracted info: {info}")