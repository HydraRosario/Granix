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
    # This pattern is made more flexible to capture the invoice number part
    # and the rest of the line, allowing for spaces within the invoice number.
    item_line_pattern = re.compile(
        r'(Fa|Re)\s+(P029[89][\s-]?\d{6,8}(?:\s*\d{1,3})?)(.*)'
    )

    # Regex to capture summary at the end
    summary_pattern = re.compile(
        r'(?:Cantidad de Facturas:\s*(\d+)\s+)?Cantidad de Remitos:\s*(\d+)\s+Bultos:\s*(\d+)'
    )

    lines = raw_ocr_text.split('\n')
    for line in lines:
        item_match = item_line_pattern.search(line)
        if item_match:
            item_type = item_match.group(1)
            raw_invoice_number_part = item_match.group(2)
            rest_of_line = item_match.group(3).strip()

            # --- 1. Extract packages first from the end of rest_of_line ---
            packages = 0
            rest_of_line_after_packages = rest_of_line
            packages_match = re.search(r'(\d+)\s*$', rest_of_line)
            if packages_match:
                packages = int(packages_match.group(1))
                # Remove the packages number from the rest of the line
                rest_of_line_after_packages = re.sub(r'(\d+)\s*$', '', rest_of_line).strip()

            # --- 2. Normalize invoice number ---
            # Combine raw_invoice_number_part and clean it
            invoice_number = re.sub(r'\s+', '', raw_invoice_number_part).strip()
            # Ensure it matches the P0298-XXXXXXXX or P0298-XXXXXXXXXX format
            invoice_number_match = re.search(r'(P029[89]-\d{6,11})', invoice_number)
            if invoice_number_match:
                invoice_number = invoice_number_match.group(1)
            else:
                logger.warning(f"Could not normalize invoice number from: {raw_invoice_number_part}")
                # Fallback to a cleaned version if the pattern doesn't match
                invoice_number = invoice_number.replace(" ", "").replace("-", "")


            commercial_entity = "No encontrado"
            delivery_address = "No encontrado"

            # --- 3. Extract address first from rest_of_line_after_packages ---
            # Improved and more strict address pattern:
            # - Looks for a street name (capitalized words, or "3 De Febrero")
            # - Followed by an optional "N°" or "N"
            # - Followed by a street number
            # - Followed by optional additional address details
            # - Ending with ", Rosario"
            address_pattern = re.compile(
                r'((?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ]*(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ]*)*\s+(?:N[°.]?\s*)?\d+)|(?:\d+\s+De Febrero\s+(?:N[°.]?\s*)?\d+))(?:,\s*[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s]*)*,\s*Rosario',
                re.IGNORECASE
            )

            address_match = address_pattern.search(rest_of_line_after_packages)

            if address_match:
                delivery_address = address_match.group(0).strip()
                # The commercial entity is everything before the address
                commercial_entity = rest_of_line_after_packages[:address_match.start()].strip()

                # --- Clean and format commercial_entity ---
                commercial_entity = commercial_entity.upper()
                # Remove standalone numbers or line prefixes from commercial_entity
                commercial_entity = re.sub(r'\b\d+\b', '', commercial_entity).strip() # Remove standalone numbers
                commercial_entity = re.sub(r'^\s*\d+\s*', '', commercial_entity).strip() # Remove leading numbers/prefixes
                # Remove common OCR errors like 'ΑΝΑ' or similar non-alphanumeric characters if they appear as noise
                commercial_entity = re.sub(r'[^\w\s.,-]', '', commercial_entity).strip()
                # Remove specific noise words like "ESQ.", "SUC.", "S.R.L." if they are not part of the main name
                commercial_entity = re.sub(r'\b(?:ESQ|SUC|S\.R\.L)\b\.?', '', commercial_entity, flags=re.IGNORECASE).strip()
                # Remove the invoice number if it somehow ended up in the commercial entity
                commercial_entity = re.sub(r'(P029[89]-\d{6,11})', '', commercial_entity).strip()


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
                # Fallback if address pattern not found, assume the whole rest_of_line_after_packages is commercial entity
                commercial_entity = rest_of_line_after_packages.upper()
                # Apply cleaning for standalone numbers even in fallback
                commercial_entity = re.sub(r'\b\d+\b', '', commercial_entity).strip()
                commercial_entity = re.sub(r'^\s*\d+\s*', '', commercial_entity).strip()
                commercial_entity = re.sub(r'[^\w\s.,-]', '', commercial_entity).strip()
                commercial_entity = re.sub(r'\b(?:ESQ|SUC|S\.R\.L)\b\.?', '', commercial_entity, flags=re.IGNORECASE).strip()
                # Remove the invoice number if it somehow ended up in the commercial entity
                commercial_entity = re.sub(r'(P029[89]-\d{6,11})', '', commercial_entity).strip()


            delivery_items.append({
                "type": item_type,
                "invoice_number": invoice_number,
                "commercial_entity": commercial_entity if commercial_entity else "No encontrado",
                "delivery_address": delivery_address,
                "packages": packages
            })

        summary_match = summary_pattern.search(line)
        if summary_match:
            if summary_match.group(1) is not None: # 'Cantidad de Facturas' was found
                total_invoices = int(summary_match.group(1))
                total_remitos = int(summary_match.group(2))
                total_packages_summary = int(summary_match.group(3))
            else: # 'Cantidad de Facturas' was NOT found, so remitos is group(2) and bultos is group(3)
                total_invoices = 0 # As per observation, if not found, it's 0
                total_remitos = int(summary_match.group(2))
                total_packages_summary = int(summary_match.group(3))

    return {
        "delivery_items": delivery_items,
        "total_invoices": total_invoices,
        "total_remitos": total_remitos,
        "total_packages_summary": total_packages_summary
    }