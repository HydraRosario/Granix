import re
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class DeliveryReportParser:
    def __init__(self):
        self.item_line_pattern = re.compile(
            r'(Fa|Re)\s+(P029[89][\s-]?\d{6,8}(?:\s*\d{1,3})?)(.*)'
        )
        self.summary_pattern = re.compile(
            r'(?:Cantidad de Facturas:\s*(\d+)\s+)?Cantidad de Remitos:\s*(\d+)\s+Bultos:\s*(\d+)'
        )
        self.packages_match_pattern = re.compile(r'(\d+)\s*$')
        self.invoice_number_normalize_pattern = re.compile(r'(P029[89]-\d{6,11})')
        self.address_pattern = re.compile(
            r'(?:.*?)((?:Pasaje|Pje\.|Alvear|San Juan|Zeballos|Velez Sarsfield|Cordiviola|Drago|Del Valle|Andrade|Sanchez De Bustamante|Corrientes|Buenos Aires|Entre Rios|Marco Polo|Ibarlucea|Nansen|Reconquista|Av. Alberdi|Balcarce|3 De Febrero|Mendoza|Rodriguez|Santiago|San Luis|Ayacucho|San Martin|Laprida|Arijon|Regimiento|Artigas|Thedy|French|Juan Jose Paso|Genova|Jose Ingenieros)(?:[\s\w,.]*?)(?:N[°.]?\s*)?\d+)(?:,\s*[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s]*)*,\s*Rosario',
            re.IGNORECASE
        )
        self.delivery_instruction_pattern = re.compile(r'Entrega:\s*(.*)', re.IGNORECASE)

    def parse_delivery_report_text(self, raw_ocr_text: str) -> dict:
        delivery_items = []
        total_invoices = 0
        total_remitos = 0
        total_packages_summary = 0

        lines = raw_ocr_text.split('\n')
        last_line_had_instruction = False

        for line in lines:
            item_match = self.item_line_pattern.search(line)
            
            if item_match:
                item_type = item_match.group(1)
                raw_invoice_number_part = item_match.group(2)
                rest_of_line = item_match.group(3).strip()

                packages, rest_of_line_after_packages = self._extract_packages(rest_of_line)
                invoice_number = self._normalize_invoice_number(raw_invoice_number_part)
                commercial_entity, delivery_address, delivery_instruction = self._extract_commercial_entity_and_address(rest_of_line_after_packages)

                delivery_items.append({
                    "type": item_type,
                    "invoice_number": invoice_number,
                    "commercial_entity": commercial_entity if commercial_entity else "No encontrado",
                    "delivery_address": delivery_address,
                    "packages": packages,
                    "delivery_instructions": delivery_instruction if delivery_instruction else "No encontrado"
                })
                
                if delivery_instruction:
                    last_line_had_instruction = True
                else:
                    last_line_had_instruction = False

            elif last_line_had_instruction and not self.summary_pattern.search(line) and line.strip():
                delivery_items[-1]["delivery_instructions"] += " " + line.strip()
            
            else:
                last_line_had_instruction = False

            summary_match = self.summary_pattern.search(line)
            if summary_match:
                total_invoices, total_remitos, total_packages_summary = self._parse_summary_line(summary_match)
                last_line_had_instruction = False

        return {
            "delivery_items": delivery_items,
            "total_invoices": total_invoices,
            "total_remitos": total_remitos,
            "total_packages_summary": total_packages_summary
        }

    def _extract_packages(self, text: str) -> tuple[int, str]:
        packages = 0
        rest_of_line_after_packages = text
        packages_match = self.packages_match_pattern.search(text)
        if packages_match:
            packages = int(packages_match.group(1))
            rest_of_line_after_packages = re.sub(self.packages_match_pattern, '', text).strip()
        return packages, rest_of_line_after_packages

    def _normalize_invoice_number(self, raw_number_part: str) -> str:
        invoice_number = re.sub(r'\s+', '', raw_number_part).strip()
        invoice_number_match = self.invoice_number_normalize_pattern.search(invoice_number)
        if invoice_number_match:
            invoice_number = invoice_number_match.group(1)
        else:
            logger.warning(f"Could not normalize invoice number from: {raw_number_part}")
            invoice_number = invoice_number.replace(" ", "").replace("-", "")
        return invoice_number

    def _extract_commercial_entity_and_address(self, text: str) -> tuple[str, str, str]:
        commercial_entity = "No encontrado"
        delivery_address = "No encontrado"
        delivery_instruction = ""

        instruction_match = self.delivery_instruction_pattern.search(text)
        if instruction_match:
            delivery_instruction = instruction_match.group(1).strip()
            text = text[:instruction_match.start()].strip()

        address_match = self.address_pattern.search(text)

        if address_match:
            delivery_address = address_match.group(1).strip()
            commercial_entity = text[:address_match.start(1)].strip()

            commercial_entity = commercial_entity.upper()
            commercial_entity = re.sub(r'\b\d+\b', '', commercial_entity).strip()
            commercial_entity = re.sub(r'^\s*\d+\s*', '', commercial_entity).strip()
            commercial_entity = re.sub(r'[^\w\s.,-]', '', commercial_entity).strip()
            commercial_entity = re.sub(r'\b(?:ESQ|SUC|S\.R\.L)\b\.?', '', commercial_entity, flags=re.IGNORECASE).strip()
            commercial_entity = re.sub(self.invoice_number_normalize_pattern, '', commercial_entity).strip()

            delivery_address = re.sub(r'\s+N[°.]?\s*', ' ', delivery_address, flags=re.IGNORECASE)

            commercial_entity_to_remove = commercial_entity.title() if commercial_entity else ""
            if commercial_entity_to_remove and commercial_entity_to_remove in delivery_address:
                delivery_address = re.sub(re.escape(commercial_entity_to_remove), '', delivery_address, flags=re.IGNORECASE).strip()

            delivery_address_parts = []
            for part in delivery_address.split(','):
                part = part.strip()
                if part.lower() == "rosario":
                    delivery_address_parts.append("Rosario")
                else:
                    delivery_address_parts.append(part.title())
            delivery_address = ", ".join(delivery_address_parts)
            delivery_address = re.sub(r'\bde\b', 'De', delivery_address)

        else:
            commercial_entity = text.upper()
            commercial_entity = re.sub(r'\b\d+\b', '', commercial_entity).strip()
            commercial_entity = re.sub(r'^\s*\d+\s*', '', commercial_entity).strip()
            commercial_entity = re.sub(r'[^\w\s.,-]', '', commercial_entity).strip()
            commercial_entity = re.sub(r'\b(?:ESQ|SUC|S\.R\.L)\b\.?', '', commercial_entity, flags=re.IGNORECASE).strip()
            commercial_entity = re.sub(self.invoice_number_normalize_pattern, '', commercial_entity).strip()

        return commercial_entity, delivery_address, delivery_instruction

    def _parse_summary_line(self, summary_match) -> tuple[int, int, int]:
        total_invoices = 0
        total_remitos = 0
        total_packages_summary = 0

        if summary_match.group(1) is not None:
            total_invoices = int(summary_match.group(1))
            total_remitos = int(summary_match.group(2))
            total_packages_summary = int(summary_match.group(3))
        else:
            total_invoices = 0
            total_remitos = int(summary_match.group(2))
            total_packages_summary = int(summary_match.group(3))
        return total_invoices, total_remitos, total_packages_summary