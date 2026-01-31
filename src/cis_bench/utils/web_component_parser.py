"""Utility for extracting data from web components with JSON attributes.

CIS WorkBench uses custom web components (wb-*) that embed data as JSON in attributes.
This module provides helpers to extract and parse that data.
"""

import html
import json
import logging
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WebComponentDataExtractor:
    """Extract JSON data from web component attributes."""

    @staticmethod
    def extract_json_attribute(
        soup: BeautifulSoup, component_name: str, attribute_name: str
    ) -> Any | None:
        """Extract and parse JSON from a web component attribute.

        Args:
            soup: BeautifulSoup parsed HTML
            component_name: Web component tag name (e.g., 'wb-benchmark-assets')
            attribute_name: Attribute containing JSON (e.g., 'assets-json')

        Returns:
            Parsed JSON data (dict or list) or None if not found

        Example:
            # HTML: <wb-benchmark-assets assets-json='[{"title":"OS","cpe_id":"..."}]'>
            assets = extract_json_attribute(soup, 'wb-benchmark-assets', 'assets-json')
            # Returns: [{'title': 'OS', 'cpe_id': '...'}]
        """
        component = soup.find(component_name)
        if not component:
            logger.debug(f"Web component not found: {component_name}")
            return None

        json_string = component.get(attribute_name)
        if not json_string:
            logger.debug(f"Attribute not found: {component_name}[{attribute_name}]")
            return None

        try:
            # HTML attributes might be HTML-encoded, decode first
            decoded = html.unescape(json_string)
            data = json.loads(decoded)
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse JSON from {component_name}[{attribute_name}]: {e}")
            return None

    @staticmethod
    def extract_html_attribute(
        soup: BeautifulSoup, component_name: str, attribute_name: str
    ) -> str | None:
        """Extract HTML-encoded content from web component attribute.

        Args:
            soup: BeautifulSoup parsed HTML
            component_name: Web component tag name
            attribute_name: Attribute containing HTML

        Returns:
            Decoded HTML string or None

        Example:
            # HTML: <wb-section text="&lt;p&gt;Overview text&lt;/p&gt;">
            html_content = extract_html_attribute(soup, 'wb-section', 'text')
            # Returns: "<p>Overview text</p>"
        """
        component = soup.find(component_name)
        if not component:
            return None

        html_string = component.get(attribute_name)
        if not html_string:
            return None

        # Decode HTML entities
        return html.unescape(html_string)

    @staticmethod
    def extract_text_from_html_attribute(
        soup: BeautifulSoup, component_name: str, attribute_name: str
    ) -> str | None:
        """Extract and convert HTML-encoded attribute to plain text.

        Args:
            soup: BeautifulSoup parsed HTML
            component_name: Web component tag name
            attribute_name: Attribute containing HTML

        Returns:
            Plain text (HTML tags stripped) or None

        Example:
            # HTML: <wb-section text="&lt;p&gt;Overview &lt;code&gt;text&lt;/code&gt;&lt;/p&gt;">
            text = extract_text_from_html_attribute(soup, 'wb-section', 'text')
            # Returns: "Overview text"
        """
        html_content = WebComponentDataExtractor.extract_html_attribute(
            soup, component_name, attribute_name
        )
        if not html_content:
            return None

        # Parse the HTML and extract text
        content_soup = BeautifulSoup(html_content, "html.parser")
        return content_soup.get_text(strip=True)
