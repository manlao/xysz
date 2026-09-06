# -*- coding: utf-8 -*-
"""
PDF→Markdown批量转换模块

支持三种PDF解析引擎（自动降级）：
1. pdfplumber（主力）— 文本提取质量好，支持表格识别
2. PyMuPDF (fitz)（备选）— 速度快，处理复杂排版更稳
3. pdfminer.six（兜底）— 兼容性最广

特性：
- 批量并行转换（多线程）
- 断点续传（skip_existing）
- 结构化MD输出（标题/段落/表格）
- 错误日志记录
"""

import hashlib
import logging
import os
import re
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

warnings.filterwarnings('ignore')

# 配置日志
logger = logging.getLogger('pdf_converter')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[PdfConverter] %(levelname)s: %(message)s'))
    logger.addHandler(handler)


class PdfConverter:
    """PDF→Markdown批量转换器。

    自动检测可用的PDF库并择优使用，支持断点续传和并行处理。
    """

    # PDF库优先级
    ENGINES = ['pdfplumber', 'fitz', 'pdfminer']

    def __init__(
        self,
        preferred_engine: Optional[str] = None,
        output_dir: str = None,
        error_log: str = None,
    ):
        """初始化转换器。

        Args:
            preferred_engine: 优先使用的PDF引擎，None则自动检测
            output_dir: MD文件输出目录（由调用方指定）
            error_log: 转换失败日志路径
        """
        self.output_dir = output_dir
        self.error_log = error_log
        self.engine = self._detect_engine(preferred_engine)
        self._failed_files: List[str] = []
        self._success_count = 0

        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)

        if self.error_log:
            fh = logging.FileHandler(error_log, encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
            logger.addHandler(fh)

    def _detect_engine(self, preferred: Optional[str] = None) -> str:
        """检测可用的PDF引擎，返回最优可用引擎名。"""
        available = []

        # 检测 pdfplumber
        try:
            import pdfplumber  # noqa: F401
            available.append('pdfplumber')
        except ImportError:
            pass

        # 检测 PyMuPDF
        try:
            import fitz  # noqa: F401
            available.append('fitz')
        except ImportError:
            pass

        # 检测 pdfminer
        try:
            from pdfminer.high_level import extract_text  # noqa: F401
            available.append('pdfminer')
        except ImportError:
            pass

        if preferred and preferred in available:
            logger.info(f"使用指定引擎: {preferred}")
            return preferred

        if not available:
            raise ImportError(
                "未找到可用的PDF库！请安装以下任一：\n"
                "  pip install pdfplumber  (推荐)\n"
                "  pip install PyMuPDF\n"
                "  pip install pdfminer.six"
            )

        engine = available[0]
        available_str = ', '.join(available)
        logger.info(f"可用引擎: {available_str}，使用: {engine}")
        return engine

    # ── 文本提取方法 ──

    def _extract_pdfplumber(self, pdf_path: str) -> Optional[str]:
        """pdfplumber 提取文本 + 表格

        策略：用两种策略提取表格（线条检测 + 文本检测），再提取纯文本，
        按页面顺序合并。避免表格内容重复出现。
        """
        import pdfplumber

        texts = []
        table_count = 0
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_parts = []

                    # 1. 提取表格：先线条策略，再文本策略（无线表格）
                    for ts in [{}, {"vertical_strategy": "text", "horizontal_strategy": "text"}]:
                        try:
                            tables = page.extract_tables(table_settings=ts)
                        except Exception:
                            tables = []
                        for table in tables:
                            if not table or len(table) < 2:
                                continue
                            md_table = self._table_to_markdown(table)
                            if md_table:
                                page_parts.append(md_table)
                                table_count += 1

                    # 2. 提取纯文本
                    try:
                        page_text = page.extract_text()
                    except Exception:
                        page_text = None
                    if page_text:
                        page_parts.insert(0, page_text)

                    if page_parts:
                        texts.append('\n\n'.join(page_parts))

            if table_count > 0:
                logger.debug(f"提取到 {table_count} 个表格: {os.path.basename(pdf_path)}")
            return '\n\n'.join(texts) if texts else None
        except Exception as e:
            logger.warning(f"pdfplumber 提取失败: {pdf_path} - {e}")
            return None

    def _extract_fitz(self, pdf_path: str) -> Optional[str]:
        """PyMuPDF (fitz) 提取文本 + 表格"""
        try:
            import fitz

            doc = fitz.open(pdf_path)
            texts = []
            table_count = 0
            for page in doc:
                page_parts = []

                # 1. 提取表格（fitz 1.23+ 支持 find_tables）
                if hasattr(page, 'find_tables'):
                    try:
                        tabs = page.find_tables()
                        for tab in tabs:
                            rows = tab.extract()
                            if rows and len(rows) >= 2:
                                md_table = self._table_to_markdown(rows)
                                if md_table:
                                    page_parts.append(md_table)
                                    table_count += 1
                    except Exception:
                        pass

                # 2. 提取纯文本
                text = page.get_text()
                if text:
                    page_parts.insert(0, text)

                if page_parts:
                    texts.append('\n\n'.join(page_parts))
            doc.close()

            if table_count > 0:
                logger.debug(f"fitz 提取到 {table_count} 个表格: {os.path.basename(pdf_path)}")
            return '\n\n'.join(texts) if texts else None
        except Exception as e:
            logger.warning(f"PyMuPDF 提取失败: {pdf_path} - {e}")
            return None

    def _extract_pdfminer(self, pdf_path: str) -> Optional[str]:
        """pdfminer.six 提取文本（兜底）"""
        try:
            from pdfminer.high_level import extract_text

            text = extract_text(pdf_path)
            return text if text.strip() else None
        except Exception as e:
            logger.warning(f"pdfminer 提取失败: {pdf_path} - {e}")
            return None

    def _extract_text(self, pdf_path: str) -> Optional[str]:
        """依次尝试各引擎提取文本，直到成功或全部失败。"""
        extractors = {
            'pdfplumber': self._extract_pdfplumber,
            'fitz': self._extract_fitz,
            'pdfminer': self._extract_pdfminer,
        }

        engine_order = [self.engine] + [e for e in self.ENGINES if e != self.engine]

        for engine in engine_order:
            if engine not in extractors:
                continue
            text = extractors[engine](pdf_path)
            if text and len(text.strip()) > 50:
                return text
            if text:
                logger.debug(f"{engine} 提取结果过短({len(text)}字符)，尝试下一引擎")

        return None

    # ── 文本结构化 → Markdown ──

    @staticmethod
    def _table_to_markdown(table: list) -> str:
        """将二维列表表格转换为Markdown表格格式。"""
        if not table or not table[0]:
            return ''

        rows = []
        for row in table:
            cleaned = [cell if cell else '' for cell in row]
            if any(c.strip() for c in cleaned):
                rows.append(cleaned)

        if not rows:
            return ''
        if len(rows) < 2:
            return ' | '.join(rows[0])

        n_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < n_cols:
                r.append('')

        md_lines = []
        md_lines.append('| ' + ' | '.join(str(c).replace('|', '\\|') for c in rows[0]) + ' |')
        md_lines.append('| ' + ' | '.join('---' for _ in range(n_cols)) + ' |')
        for row in rows[1:]:
            md_lines.append('| ' + ' | '.join(str(c).replace('|', '\\|') for c in row) + ' |')

        return '\n'.join(md_lines)

    @staticmethod
    def _text_to_markdown(text: str) -> str:
        """将提取的原始文本转换为结构化Markdown。"""
        lines = text.split('\n')
        md_lines = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            if not line:
                md_lines.append('')
                i += 1
                continue

            # 跳过已经是 MD 表格的行（以 | 开头），保持原样
            if line.startswith('|'):
                md_lines.append(line)
                i += 1
                continue

            if len(line) < 60 and (line.isupper() or re.match(r'^[\d一二三四五六七八九十]+[、.．）\)]', line)):
                md_lines.append(f'## {line}')
                i += 1
                continue

            if re.match(r'^第[一二三四五六七八九十百]+[章节条]', line):
                md_lines.append(f'### {line}')
                i += 1
                continue

            if re.match(r'^[\d一二三四五六七八九十]+[、.．）\)]', line):
                md_lines.append(f'- {line}')
                i += 1
                continue

            paragraph_lines = []
            while i < len(lines) and lines[i].strip():
                paragraph_lines.append(lines[i].strip())
                i += 1

            paragraph = ' '.join(paragraph_lines)
            md_lines.append(paragraph)
            i += 1

        return '\n\n'.join(md_lines)

    # ── 转换核心逻辑 ──

    def convert_one(self, pdf_path: str, source_id: Optional[str] = None) -> Optional[str]:
        """转换单个PDF文件为Markdown。

        Args:
            pdf_path: PDF文件路径
            source_id: 公告资源ID，用作MD文件名。不传则用PDF文件名的hash。

        Returns:
            生成的MD文件路径，失败返回None。
        """
        if not os.path.exists(pdf_path):
            logger.error(f"文件不存在: {pdf_path}")
            self._failed_files.append(pdf_path)
            return None

        if source_id is None:
            name_hash = hashlib.md5(os.path.basename(pdf_path).encode()).hexdigest()[:12]
            source_id = name_hash

        md_filename = f'{source_id}.md'
        md_path = os.path.join(self.output_dir, md_filename)

        if os.path.exists(md_path) and os.path.getsize(md_path) > 100:
            logger.debug(f"跳过已转换: {md_filename}")
            return md_path

        raw_text = self._extract_text(pdf_path)
        if raw_text is None:
            logger.error(f"所有引擎提取失败: {pdf_path}")
            self._failed_files.append(pdf_path)
            return None

        md_text = self._text_to_markdown(raw_text)

        header = (
            f'<!--\n'
            f'  source_id: {source_id}\n'
            f'  source_file: {os.path.basename(pdf_path)}\n'
            f'  engine: {self.engine}\n'
            f'-->\n\n'
        )

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(header + md_text)

        return md_path

    def convert_batch(
        self,
        pdf_paths: Dict[str, str],
        skip_existing: bool = True,
        max_workers: int = 4,
    ) -> Dict[str, str]:
        """批量转换PDF为Markdown（多线程并行）。

        Args:
            pdf_paths: {source_id: pdf_path} 字典
            skip_existing: 是否跳过已存在的MD文件
            max_workers: 并行线程数

        Returns:
            {source_id: md_path} 字典，仅包含成功转换的文件。
        """
        total = len(pdf_paths)
        if total == 0:
            logger.info("无PDF文件需要转换")
            return {}

        to_convert = {}
        skipped = 0
        for sid, pdf_path in pdf_paths.items():
            md_path = os.path.join(self.output_dir, f'{sid}.md')
            if skip_existing and os.path.exists(md_path) and os.path.getsize(md_path) > 100:
                skipped += 1
            else:
                to_convert[sid] = pdf_path

        logger.info(f"待转换: {len(to_convert)} 篇, 已跳过: {skipped} 篇, 共: {total} 篇")
        if not to_convert:
            return {sid: os.path.join(self.output_dir, f'{sid}.md')
                    for sid in pdf_paths}

        self._success_count = 0
        self._failed_files = []

        results = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(to_convert))) as executor:
            futures = {
                executor.submit(self.convert_one, pdf_path, sid): sid
                for sid, pdf_path in to_convert.items()
            }

            for future in as_completed(futures):
                sid = futures[future]
                try:
                    md_path = future.result()
                    if md_path:
                        results[sid] = md_path
                        self._success_count += 1
                except Exception as e:
                    logger.error(f"转换异常 {sid}: {e}")
                    self._failed_files.append(sid)

        for sid in pdf_paths:
            if sid not in results:
                md_path = os.path.join(self.output_dir, f'{sid}.md')
                if os.path.exists(md_path) and os.path.getsize(md_path) > 100:
                    results[sid] = md_path

        logger.info(
            f"转换完成: 成功 {self._success_count}/{len(to_convert)}, "
            f"总计 {len(results)}/{total}, 失败 {len(self._failed_files)}"
        )

        return results

    def get_failed_files(self) -> List[str]:
        """获取转换失败的文件列表。"""
        return self._failed_files
