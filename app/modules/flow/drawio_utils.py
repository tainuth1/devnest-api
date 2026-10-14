import base64
import html
import re
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
import zlib
from datetime import datetime
from typing import Any

DEFAULT_MXGRAPH_XML = (
    '<mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" '
    'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1050" pageHeight="1485" '
    'background="#FFFFFF" math="0" shadow="0">'
    '<root>'
    '<mxCell id="0"/>'
    '<mxCell id="1" parent="0"/>'
    '</root>'
    '</mxGraphModel>'
)


def compress_xml(xml_str: str) -> str:
    """
    Draw.io deflation algorithm matching Graph.compress:
    URL-encode -> raw DEFLATE (wbits=-15) -> Base64 encode.
    """
    quoted = urllib.parse.quote(xml_str, safe="~()*!'")
    compressor = zlib.compressobj(
        level=9,
        method=zlib.DEFLATED,
        wbits=-15,
        memLevel=8,
        strategy=0,
    )
    compressed = compressor.compress(quoted.encode("utf-8")) + compressor.flush()
    return base64.b64encode(compressed).decode("ascii")


def decompress_xml(b64_str: str) -> str:
    """
    Draw.io inflation algorithm matching Graph.decompress:
    Base64 decode -> raw INFLATE (wbits=-15) -> URL-decode.
    """
    try:
        raw = base64.b64decode(b64_str.strip())
        decompressed = zlib.decompress(raw, wbits=-15)
        return urllib.parse.unquote(decompressed.decode("utf-8"))
    except Exception:
        # If decompression fails, try standard zlib decompression
        try:
            decompressed = zlib.decompress(raw)
            return urllib.parse.unquote(decompressed.decode("utf-8"))
        except Exception:
            return b64_str


def parse_page_model_attributes(model_elem: ET.Element) -> dict[str, Any]:
    """
    Extracts canvas layout metadata directly from <mxGraphModel> attributes.
    """
    bg = model_elem.attrib.get("background", "#FFFFFF")
    if not bg or bg == "none":
        bg = "#FFFFFF"

    page_width = 1050
    if "pageWidth" in model_elem.attrib:
        try:
            page_width = int(float(model_elem.attrib["pageWidth"]))
        except (ValueError, TypeError):
            pass

    page_height = 1485
    if "pageHeight" in model_elem.attrib:
        try:
            page_height = int(float(model_elem.attrib["pageHeight"]))
        except (ValueError, TypeError):
            pass

    grid_enabled = model_elem.attrib.get("grid", "1") != "0"

    grid_size = 10
    if "gridSize" in model_elem.attrib:
        try:
            grid_size = int(float(model_elem.attrib["gridSize"]))
        except (ValueError, TypeError):
            pass

    return {
        "background_color": bg,
        "page_width": page_width,
        "page_height": page_height,
        "grid_enabled": grid_enabled,
        "grid_size": grid_size,
    }


def parse_mxfile(xml_text: str) -> list[dict[str, Any]]:
    """
    Parses a Draw.io XML payload into a list of individual canvas page definitions.
    Supports:
      1. Multi-page <mxfile><diagram id="..." name="...">...</diagram></mxfile>
      2. Single <diagram id="..." name="...">...</diagram>
      3. Bare <mxGraphModel>...</mxGraphModel>
    Handles both uncompressed and compressed <diagram> contents.
    """
    cleaned = xml_text.strip()
    if not cleaned:
        return [
            {
                "drawio_page_id": "page_001",
                "name": "Page-1",
                "xml_content": DEFAULT_MXGRAPH_XML,
                "compressed_xml": None,
                "background_color": "#FFFFFF",
                "grid_enabled": True,
                "grid_size": 10,
                "page_width": 1050,
                "page_height": 1485,
                "page_order": 0,
            }
        ]

    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as e:
        raise ValueError(f"Invalid Draw.io XML document: {e}")

    tag = root.tag.lower()
    pages_data = []

    if tag == "mxfile":
        diagram_elements = root.findall("./diagram")
        if not diagram_elements:
            diagram_elements = root.findall(".//diagram")

        for idx, diag_el in enumerate(diagram_elements):
            p_id = diag_el.attrib.get("id") or f"page_{idx + 1:03d}"
            p_name = diag_el.attrib.get("name") or f"Page-{idx + 1}"

            # Check if there's a child <mxGraphModel> or compressed text
            model_el = diag_el.find("./mxGraphModel")
            if model_el is not None:
                xml_content = ET.tostring(model_el, encoding="utf-8").decode("utf-8")
                attrs = parse_page_model_attributes(model_el)
            else:
                text_content = (diag_el.text or "").strip()
                if text_content:
                    decompressed = decompress_xml(text_content)
                    if "<mxGraphModel" in decompressed:
                        try:
                            decomp_el = ET.fromstring(decompressed)
                            xml_content = ET.tostring(decomp_el, encoding="utf-8").decode("utf-8")
                            attrs = parse_page_model_attributes(decomp_el)
                        except Exception:
                            xml_content = decompressed
                            attrs = {
                                "background_color": "#FFFFFF",
                                "page_width": 1050,
                                "page_height": 1485,
                                "grid_enabled": True,
                                "grid_size": 10,
                            }
                    else:
                        xml_content = DEFAULT_MXGRAPH_XML
                        attrs = {
                            "background_color": "#FFFFFF",
                            "page_width": 1050,
                            "page_height": 1485,
                            "grid_enabled": True,
                            "grid_size": 10,
                        }
                else:
                    xml_content = DEFAULT_MXGRAPH_XML
                    attrs = {
                        "background_color": "#FFFFFF",
                        "page_width": 1050,
                        "page_height": 1485,
                        "grid_enabled": True,
                        "grid_size": 10,
                    }

            pages_data.append(
                {
                    "drawio_page_id": p_id,
                    "name": p_name,
                    "xml_content": xml_content,
                    "compressed_xml": None,
                    "page_order": idx,
                    **attrs,
                }
            )

    elif tag == "diagram":
        p_id = root.attrib.get("id") or "page_001"
        p_name = root.attrib.get("name") or "Page-1"
        model_el = root.find("./mxGraphModel")
        if model_el is not None:
            xml_content = ET.tostring(model_el, encoding="utf-8").decode("utf-8")
            attrs = parse_page_model_attributes(model_el)
        else:
            text_content = (root.text or "").strip()
            decompressed = decompress_xml(text_content) if text_content else DEFAULT_MXGRAPH_XML
            try:
                decomp_el = ET.fromstring(decompressed)
                xml_content = ET.tostring(decomp_el, encoding="utf-8").decode("utf-8")
                attrs = parse_page_model_attributes(decomp_el)
            except Exception:
                xml_content = DEFAULT_MXGRAPH_XML
                attrs = {
                    "background_color": "#FFFFFF",
                    "page_width": 1050,
                    "page_height": 1485,
                    "grid_enabled": True,
                    "grid_size": 10,
                }
        pages_data.append(
            {
                "drawio_page_id": p_id,
                "name": p_name,
                "xml_content": xml_content,
                "compressed_xml": None,
                "page_order": 0,
                **attrs,
            }
        )

    elif tag == "mxgraphmodel":
        attrs = parse_page_model_attributes(root)
        xml_content = ET.tostring(root, encoding="utf-8").decode("utf-8")
        pages_data.append(
            {
                "drawio_page_id": "page_001",
                "name": "Page-1",
                "xml_content": xml_content,
                "compressed_xml": None,
                "page_order": 0,
                **attrs,
            }
        )
    else:
        raise ValueError(f"Unrecognized root XML element: <{root.tag}>. Expected <mxfile>, <diagram>, or <mxGraphModel>.")

    if not pages_data:
        pages_data.append(
            {
                "drawio_page_id": "page_001",
                "name": "Page-1",
                "xml_content": DEFAULT_MXGRAPH_XML,
                "compressed_xml": None,
                "background_color": "#FFFFFF",
                "grid_enabled": True,
                "grid_size": 10,
                "page_width": 1050,
                "page_height": 1485,
                "page_order": 0,
            }
        )

    return pages_data


def build_mxfile(
    pages: list[Any],
    modified: datetime | None = None,
    version: str = "24.7.17",
    host: str = "dev-nest",
) -> str:
    """
    Assembles a full Draw.io <mxfile> XML document containing all given pages.
    Compatible with Draw.io embed action 'load' and standard Draw.io file exports.
    """
    mod_str = modified.isoformat() if modified else datetime.utcnow().isoformat() + "Z"
    lines = [f'<mxfile host="{host}" modified="{mod_str}" agent="DevNest" version="{version}">']

    sorted_pages = sorted(pages, key=lambda p: getattr(p, "page_order", 0) if not isinstance(p, dict) else p.get("page_order", 0))

    for p in sorted_pages:
        if isinstance(p, dict):
            p_id = p.get("drawio_page_id") or "page_001"
            p_name = html.escape(p.get("name") or "Page-1")
            content = p.get("xml_content") or DEFAULT_MXGRAPH_XML
        else:
            p_id = getattr(p, "drawio_page_id", "page_001")
            p_name = html.escape(getattr(p, "name", "Page-1"))
            content = getattr(p, "xml_content", DEFAULT_MXGRAPH_XML)

        content_clean = content.strip()
        lines.append(f'  <diagram id="{p_id}" name="{p_name}">')
        lines.append(f"    {content_clean}")
        lines.append("  </diagram>")

    lines.append("</mxfile>")
    return "\n".join(lines)


def build_default_diagram_pages(title: str = "System Architecture") -> list[dict[str, Any]]:
    """
    Generates standard initial Page-1 for a newly created diagram.
    """
    return [
        {
            "drawio_page_id": str(uuid.uuid4())[:8],
            "name": "Page-1",
            "xml_content": DEFAULT_MXGRAPH_XML,
            "compressed_xml": None,
            "background_color": "#FFFFFF",
            "grid_enabled": True,
            "grid_size": 10,
            "page_width": 1050,
            "page_height": 1485,
            "page_order": 0,
        }
    ]



def sanitize_filename(name: str) -> str:
    """
    Sanitizes title for safe file download naming.
    """
    clean = re.sub(r'[\/:*?"<>|]', "_", name).strip()
    return clean or "diagram"
