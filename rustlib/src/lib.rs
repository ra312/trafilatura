use scraper::{Html, Selector};

/// Simplified representation of extracted data
#[derive(Debug, Default, Clone)]
pub struct Document {
    pub body: String,
    pub text: String,
}

/// Configuration options mirroring the Python `Extractor` struct
#[derive(Debug, Clone)]
pub struct Extractor {
    pub output_format: String,
    pub formatting: bool,
    pub links: bool,
    pub images: bool,
    pub tables: bool,
}

impl Extractor {
    pub fn new(
        output_format: &str,
        include_tables: bool,
        include_images: bool,
        include_formatting: bool,
        include_links: bool,
    ) -> Self {
        Self {
            output_format: output_format.to_string(),
            formatting: include_formatting,
            links: include_links,
            images: include_images,
            tables: include_tables,
        }
    }
}

/// Extract text content from the provided HTML string.
///
/// This mirrors the behaviour of the Python `_internal_extraction` function
/// but implements a very small subset of its capabilities. It only parses the
/// HTML and collects all text into the `Document` structure.
pub fn _internal_extraction(
    filecontent: &str,
    output_format: &str,
    include_tables: bool,
    include_images: bool,
    include_formatting: bool,
    include_links: bool,
) -> Option<Document> {
    let _options = Extractor::new(
        output_format,
        include_tables,
        include_images,
        include_formatting,
        include_links,
    );

    // Parse HTML into a DOM tree
    let tree = Html::parse_document(filecontent);

    // Collect text from all nodes
    let selector = Selector::parse("body").ok()?;
    let mut text = String::new();
    for element in tree.select(&selector) {
        text.push_str(&element.text().collect::<Vec<_>>().join(" "));
    }

    if text.trim().is_empty() {
        return None;
    }

    let document = Document {
        body: filecontent.to_string(),
        text,
    };

    Some(document)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn basic_extraction() {
        let html = "<html><body><p>Hello</p><p>world!</p></body></html>";
        let doc = _internal_extraction(html, "txt", true, false, false, false)
            .expect("should return document");
        assert_eq!(doc.text, "Hello world!");
    }
}
