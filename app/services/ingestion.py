import os
import tempfile
import uuid
import re
from unstructured.partition.pdf import partition_pdf


class IngestionService:

    def extract_sections(self, file_bytes: bytes, filename: str) -> list[dict]:
        """
        Extrae el contenido del PDF y lo organiza en secciones
        detectando títulos cuando sea posible.
        Utiliza strategy="fast" para máxima estabilidad en contenedor.
        """

        temp_dir = tempfile.gettempdir()
        temp_name = f"{uuid.uuid4()}_{filename}"
        temp_path = os.path.join(temp_dir, temp_name)

        with open(temp_path, "wb") as f:
            f.write(file_bytes)

        try:
    
            elements = partition_pdf(
                filename=temp_path,
                strategy="fast"
            )

            sections = []
            current_section = {
                "title": None,
                "content": []
            }

            for el in elements:

                if not hasattr(el, "text") or not el.text:
                    continue

                text = el.text.strip()

                if len(text) < 10:
                    continue

                # Detectar títulos por categoría o heurística simple
                if getattr(el, "category", None) == "Title" or self._looks_like_title(text):

                    # Guardar sección anterior si tiene contenido
                    if current_section["content"]:
                        sections.append(current_section)

                    current_section = {
                        "title": text,
                        "content": []
                    }

                else:
                    current_section["content"].append(text)

            # Agregar última sección
            if current_section["content"]:
                sections.append(current_section)

            # Normalización final por sección
            structured_sections = []

            for idx, sec in enumerate(sections):
                content = "\n".join(sec["content"])
                content = self._normalize_text(content)

                structured_sections.append({
                    "title": sec["title"],
                    "content": content,
                    "section_index": idx
                })

            return structured_sections

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _normalize_text(self, text: str) -> str:
        """
        Limpieza básica para PDFs institucionales.
        """

        text = text.replace("\r\n", "\n")

        # Unir palabras cortadas por salto de línea
        text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)

        # Compactar múltiples saltos
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _looks_like_title(self, text: str) -> bool:
        """
        Heurística simple para detectar títulos en strategy="fast".
        """

        # Muy largo no es título
        if len(text) > 120:
            return False

        # Si todo está en mayúsculas
        if text.isupper():
            return True

        # Si comienza con palabras típicas de estructura académica
        if re.match(r"^(Unidad|Tema|Capítulo|Modulo|Módulo|Objetivo|Competencia)", text):
            return True

        return False