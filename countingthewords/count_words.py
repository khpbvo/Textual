#!/usr/bin/env python3
"""
A Python script to count words in a TXT, PDF, DOCX, or HTML file.

It supports reading from one or more files or standard input. For PDF files, it uses PyPDF2 for text extraction, for DOCX files it uses python-docx, and for HTML files it uses BeautifulSoup from beautifulsoup4.

Improvements:
- Modularized logger configuration using a dedicated function.
- Enhanced logging format to include timestamps.
- Cleaner logger initialization to avoid multiple handler attachments.
- Minor code refactoring for readability.
- Added additional debug statements for better traceability.
"""

import sys
import re
import argparse
from pathlib import Path
import logging


def configure_logger(verbose: bool = False) -> logging.Logger:
    """
    Configure and return a logger with the given verbosity level.
    """
    logger = logging.getLogger("count_words")
    # Avoid adding multiple handlers if already configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    return logger


# Precompile regex for word matching
WORD_REGEX = re.compile(r"\b[\w']+\b")


def count_words(text: str) -> int:
    """
    Count the number of words in the given text.

    Args:
        text (str): Text to count words in.

    Returns:
        int: Number of words.
    """
    logger = logging.getLogger("count_words")
    logger.debug("Starting count_words function.")
    words = WORD_REGEX.findall(text)
    count = len(words)
    logger.debug(f"Counted {count} words in given text.")
    return count


def read_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file using PyPDF2.

    Args:
        file_path (str): Path to the PDF file.

    Returns:
        str: Extracted text with page breaks.

    Raises:
        ImportError: If PyPDF2 is not installed.
        Exception: For issues in reading PDF.
    """
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise ImportError("PyPDF2 library is required to read PDF files. Install it with 'pip install PyPDF2'")
    
    logger = logging.getLogger("count_words")
    logger.debug(f"Starting to read PDF file: {file_path}")
    
    try:
        reader = PdfReader(file_path)
    except Exception as e:
        raise Exception(f"Failed to read PDF file: {e}")

    full_text = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text()
            if page_text:
                full_text.append(page_text)
            else:
                logger.warning(f"No text extracted from page {i} of {file_path}.")
        except Exception as e:
            logger.error(f"Error extracting text from page {i} of {file_path}: {e}")
    return "\n".join(full_text)


def read_docx(file_path: str) -> str:
    """
    Extract text from a DOCX file using python-docx.

    Args:
        file_path (str): Path to the DOCX file.

    Returns:
        str: Extracted text.

    Raises:
        ImportError: If python-docx is not installed.
        Exception: For issues in reading the DOCX file.
    """
    try:
        import docx
    except ImportError:
        raise ImportError("python-docx library is required to read DOCX files. Install it with 'pip install python-docx'")

    logger = logging.getLogger("count_words")
    logger.debug(f"Starting to read DOCX file: {file_path}")

    try:
        doc = docx.Document(file_path)
    except Exception as e:
        raise Exception(f"Failed to read DOCX file: {e}")

    full_text = [p.text for p in doc.paragraphs if p.text]
    return "\n".join(full_text)


def read_html(file_path: str) -> str:
    """
    Extract text from an HTML file using BeautifulSoup.

    Args:
        file_path (str): Path to the HTML file.

    Returns:
        str: Extracted text.

    Raises:
        ImportError: If beautifulsoup4 is not installed.
        Exception: For issues in reading the HTML file.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("beautifulsoup4 library is required to read HTML files. Install it with 'pip install beautifulsoup4'")

    logger = logging.getLogger("count_words")
    logger.debug(f"Starting to read HTML file: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        raise Exception(f"Failed to read HTML file: {e}")

    soup = BeautifulSoup(html_content, 'html.parser')
    return soup.get_text()


def read_text_file(file_path: str) -> str:
    """
    Read text from a plain text file.

    Args:
        file_path (str): Path to the text file.

    Returns:
        str: Content of the file.

    Raises:
        Exception: For issues in reading file.
    """
    logger = logging.getLogger("count_words")
    logger.debug(f"Starting to read text file: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise Exception(f"Failed to read text file '{file_path}': {e}")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(
        description='Count words in a TXT, PDF, DOCX, or HTML file with modular logging and multi-file support.'
    )
    parser.add_argument('files', nargs='*', help='Paths to the input file(s). If omitted, reads from stdin.')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--version', action='version', version='count_words 1.3')
    args = parser.parse_args()
    logger = logging.getLogger("count_words")
    logger.debug(f"Parsed arguments: {args}")
    return args


def process_file(file_path: str) -> int:
    """
    Process a single file and count words.

    Args:
        file_path (str): Path to the input file.

    Returns:
        int: Word count.

    Raises:
        FileNotFoundError: If file does not exist.
    """
    logger = logging.getLogger("count_words")
    logger.debug(f"Processing file: {file_path}")
    path_obj = Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Error: File '{file_path}' does not exist.")
    ext = path_obj.suffix.lower()
    logger.debug(f"File extension detected: {ext}")
    if ext == '.pdf':
        logger.debug("Detected PDF file format.")
        text = read_pdf(file_path)
    elif ext == '.docx':
        logger.debug("Detected DOCX file format.")
        text = read_docx(file_path)
    elif ext in ('.html', '.htm'):
        logger.debug("Detected HTML file format.")
        text = read_html(file_path)
    else:
        logger.debug("Detected plain text file or unsupported extension, defaulting to text file reader.")
        text = read_text_file(file_path)
    return count_words(text)


def main() -> None:
    args = parse_arguments()

    # Configure logger based on verbosity
    global logger
    logger = configure_logger(args.verbose)
    logger.debug("Logger configured in main function.")

    try:
        if args.files:
            total = 0
            for file in args.files:
                try:
                    logger.info(f"Processing file: {file}")
                    count = process_file(file)
                    print(f"{file}: {count} words")
                    total += count
                except Exception as e:
                    logger.error(f"Failed to process {file}: {e}")
            if len(args.files) > 1:
                print(f"Total words across all files: {total}")
        else:
            logger.info("Reading from standard input...")
            input_text = sys.stdin.read()
            count = count_words(input_text)
            print(f"Total words: {count}")
    except Exception as e:
        logger.error(f"Error processing input: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
