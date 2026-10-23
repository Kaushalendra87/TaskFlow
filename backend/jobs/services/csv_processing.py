import csv
import io


class CSVValidationError(ValueError):
    """Raised when an uploaded file is not a valid UTF-8 CSV."""


def iter_csv_rows(file_obj):
    """Yield CSV records as dictionaries while validating the table shape."""
    raw_file = getattr(file_obj, "file", file_obj)
    position = raw_file.tell()
    text_file = io.TextIOWrapper(
        raw_file,
        encoding="utf-8-sig",
        newline="",
    )

    try:
        reader = csv.reader(text_file, strict=True)
        headers = next(reader, None)
        if not headers or not any(header.strip() for header in headers):
            raise CSVValidationError("The CSV must contain a header row.")

        headers = [header.strip() for header in headers]
        if any(not header for header in headers):
            raise CSVValidationError("CSV column names cannot be empty.")
        if len(set(headers)) != len(headers):
            raise CSVValidationError("CSV column names must be unique.")

        for values in reader:
            if not values or not any(value.strip() for value in values):
                continue
            if len(values) != len(headers):
                raise CSVValidationError(
                    f"CSV row {reader.line_num} has {len(values)} values; "
                    f"expected {len(headers)}."
                )
            yield dict(zip(headers, values))
    except UnicodeDecodeError as exc:
        raise CSVValidationError(
            "The CSV must be encoded as UTF-8."
        ) from exc
    except csv.Error as exc:
        raise CSVValidationError(
            f"The CSV format is invalid: {exc}"
        ) from exc
    finally:
        text_file.detach()
        raw_file.seek(position)
