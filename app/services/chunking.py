import tiktoken
from typing import List, Dict
from langchain.text_splitter import RecursiveCharacterTextSplitter


class ChunkingService:

    def __init__(
        self,
        chunk_size: int = 600,
        chunk_overlap: int = 120,
        min_chunk_tokens: int = 50
    ):
        # Tokenizer estable compatible con embeddings modernos
        self.encoding = tiktoken.get_encoding("cl100k_base")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_tokens = min_chunk_tokens

        self.size_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=[
                "\n\n",
                "\n",
                ". ",
                " "
            ],
            length_function=self._token_length
        )

    # ============================================================
    # Token length real
    # ============================================================

    def _token_length(self, text: str) -> int:
        return len(self.encoding.encode(text))

    # ============================================================
    # Chunk principal
    # ============================================================

    def chunk_sections(self, sections: List[Dict]) -> List[Dict]:

        final_chunks = []

        for idx, sec in enumerate(sections):

            title = sec.get("title")
            content = sec.get("content", "")

            if not content:
                continue

            total_tokens = self._token_length(content)

            # Si la sección ya es del tamaño correcto
            if total_tokens <= self.chunk_size:

                if total_tokens >= self.min_chunk_tokens:
                    final_chunks.append({
                        "title": title,
                        "content": content,
                        "section_index": idx,
                        "token_length": total_tokens
                    })

                continue

            # Si es grande → dividir por tokens
            sub_chunks = self.size_splitter.split_text(content)

            for sub_idx, sub in enumerate(sub_chunks):

                token_len = self._token_length(sub)

                if token_len < self.min_chunk_tokens:
                    continue

                final_chunks.append({
                    "title": title,
                    "content": sub,
                    "section_index": idx,
                    "sub_index": sub_idx,
                    "token_length": token_len
                })

        return final_chunks