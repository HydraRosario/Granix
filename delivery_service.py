import re
import logging

# Configurar logger para delivery_service.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def parse_delivery_report_text(raw_ocr_text: str) -> dict:
    """
    Extrae datos estructurados del texto OCR de un informe de reparto.
    """
    delivery_items = []
    total_invoices = 0
    total_remitos = 0
    total_packages_summary = 0

    # Regex to capture Type, InvoiceNumber, and the rest of the line
    item_line_pattern = re.compile(
        r'(Fa|Re)\s+([A-Z0-9-]+)\s+(.*)'
    )

    # Regex to capture summary at the end
    summary_pattern = re.compile(
        r'Cantidad de Facturas:\s*(\d+)\s+Cantidad de Remitos:\s*(\d+)\s+Bultos:\s*(\d+)'
    )

    lines = raw_ocr_text.split('\n')
    for line in lines:
        item_match = item_line_pattern.search(line)
        if item_match:
            item_type = item_match.group(1)
            invoice_number = item_match.group(2)
            rest_of_line = item_match.group(3).strip()

            # Extract packages from the end of rest_of_line
            packages_match = re.search(r'(\d+)$', rest_of_line)
            packages = 0
            if packages_match:
                packages = int(packages_match.group(1))
                rest_of_line_without_packages = rest_of_line[:-len(packages_match.group(0))].strip()
            else:
                rest_of_line_without_packages = rest_of_line

            commercial_entity = "No encontrado"
            delivery_address = "No encontrado"

            # Updated address pattern:
            # - Starts with a capitalized word (street name)
            # - Followed by optional "N°" or "N" (case-insensitive)
            # - Followed by a number
            # - Followed by optional additional address details, including "Rosario"
            # This pattern aims to capture the entire address part.
            address_pattern = re.compile(
                r'([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s]*?\s+(?:N[°.]?\s*\d+|\d+)(?:,\s*[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s]*)*)',
                re.IGNORECASE
            )

            address_match = address_pattern.search(rest_of_line_without_packages)

            if address_match:
                # Extract the potential address part
                potential_address = address_match.group(0).strip()

                # Separate commercial entity and delivery address
                commercial_entity = rest_of_line_without_packages[:address_match.start()].strip()
                delivery_address = potential_address

                # --- Clean and format commercial_entity ---
                commercial_entity = commercial_entity.upper()
                # Remove standalone numbers or line prefixes from commercial_entity
                commercial_entity = re.sub(r'\b\d+\b', '', commercial_entity).strip() # Remove standalone numbers
                commercial_entity = re.sub(r'^\s*\d+\s*', '', commercial_entity).strip() # Remove leading numbers/prefixes

                # --- Clean and format delivery_address ---
                # Remove "N" or "N°" between street and number
                delivery_address = re.sub(r'\s+N[°.]?\s*', ' ', delivery_address, flags=re.IGNORECASE)

                # Format to title case, ensuring "Rosario" remains "Rosario"
                delivery_address_parts = []
                for part in delivery_address.split(','):
                    part = part.strip()
                    if part.lower() == "rosario":
                        delivery_address_parts.append("Rosario")
                    else:
                        delivery_address_parts.append(part.title())
                delivery_address = ", ".join(delivery_address_parts)

            else:
                # Fallback if address pattern not found
                commercial_entity = rest_of_line_without_packages.upper()
                # Apply cleaning for standalone numbers even in fallback
                commercial_entity = re.sub(r'\b\d+\b', '', commercial_entity).strip()
                commercial_entity = re.sub(r'^\s*\d+\s*', '', commercial_entity).strip()

            delivery_items.append({
                "type": item_type,
                "invoice_number": invoice_number,
                "commercial_entity": commercial_entity,
                "delivery_address": delivery_address,
                "packages": packages
            })
        
        summary_match = summary_pattern.search(line)
        if summary_match:
            total_invoices = int(summary_match.group(1))
            total_remitos = int(summary_match.group(2))
            total_packages_summary = int(summary_match.group(3))

    return {
        "delivery_items": delivery_items,
        "total_invoices": total_invoices,
        "total_remitos": total_remitos,
        "total_packages_summary": total_packages_summary
    }
