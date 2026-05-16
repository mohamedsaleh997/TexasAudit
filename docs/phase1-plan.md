# Phase 1: UI/Visual Comparison - Implementation Plan

## Overview

**Goal:** Compare uploaded PDF brand guide against crawled website to generate a detailed report of dimension mismatches, missing/extra images, broken images, and format issues.

**Flow:**
```
User uploads PDF → GuideExtractor extracts text + images per page
                          ↓
UIComparisonEngine (NEW) parses spec text → list[GuideImageSpec]
                          ↓
SiteCrawler crawls website → collects all image evidence (width, height, src, loaded)
                          ↓
UIComparisonEngine compares:
  1. Match guide spec → website evidence by label + dimensions
  2. Check exact dimension match (no tolerance)
  3. Check format match (PNG vs JPG)
  4. Flag broken/untracked images
                          ↓
ComparisonReport → Streamlit renders with screenshot + severity
```

---

## Decision Summary

| Question | Decision |
|----------|----------|
| Missing alt text severity | Warning |
| Untracked images handling | Only report if broken, ignore healthy extras |
| Max links checked | Configurable (not hardcoded to 80) |
| Without guide PDF | Run basic image health check (broken, unloaded, missing alt) |
| Broken links | Already implemented via Functional checks |

---

## What Will Be Built

### New Files (6 total)

**Models:**
1. `app/models/guide_image_spec.py` - Image spec from PDF (name, width, height, format)
2. `app/models/comparison_result.py` - ComparisonIssue, ComparisonSeverity, ComparisonResult
3. `app/models/comparison_report.py` - Aggregated report with helper properties

**Services:**
4. `app/services/guide_spec_parser.py` - Parse PDF text → list[GuideImageSpec]
5. `app/services/image_matcher.py` - Match guide specs → website images (with ambiguity detection)
6. `app/services/ui_comparison_engine.py` - Orchestrate comparison, handle both guide/no-guide modes

### Modified Files (4 total)

1. `app/models/test_result.py` - Add `CheckType.UI_COMPARISON`
2. `app/services/website_health_auditor.py` - Add `CheckType.UI_COMPARISON` handling, make MAX_LINKS configurable
3. `app/ui/streamlit_app.py` - Add `_render_comparison_report()` section
4. `config/websites.yaml` - Add `max_links_to_check` per website (optional field, default 80)

---

## Models

### GuideImageSpec (`app/models/guide_image_spec.py`)

```python
class GuideImageSpec(BaseModel):
    page_number: int
    image_name: str          # "Hero Banner Desktop"
    expected_width: int      # 1280
    expected_height: int     # 720
    format: str              # "PNG", "JPG"
    notes: str               # "Lossy", "Lossless", etc.
```

### ComparisonIssue (`app/models/comparison_result.py`)

```python
class ComparisonIssue(str, Enum):
    MISSING_IMAGE = "Image from guide not found on website"
    DIMENSION_MISMATCH = "Dimensions do not match guide spec"
    FORMAT_MISMATCH = "Format does not match guide spec"
    BROKEN_IMAGE = "Image failed to load"
    UNTRACKED_BROKEN = "Untracked website image is broken"
    AMBIGUOUS_MATCH = "Multiple website images could match this guide spec"
    MISSING_ALT = "Image is missing alt text"
```

### ComparisonSeverity (`app/models/comparison_result.py`)

```python
class ComparisonSeverity(str, Enum):
    CRITICAL = "Critical"   # Missing, wrong dimensions, wrong format, broken
    WARNING = "Warning"    # Ambiguous match, untracked broken, missing alt
    PASSED = "Passed"      # All checks pass
```

### ComparisonResult (`app/models/comparison_result.py`)

```python
class ComparisonResult(BaseModel):
    guide_spec: GuideImageSpec | None
    matched_website_image: ImageEvidence | None
    issue: ComparisonIssue
    severity: ComparisonSeverity
    expected_dimensions: tuple[int, int]
    actual_dimensions: tuple[int, int] | None
    page_url: str | None    # Which website page the image was found on
    details: str
    screenshot_path: str | None  # Annotated screenshot of the issue
```

### ComparisonReport (`app/models/comparison_report.py`)

```python
class ComparisonReport(BaseModel):
    guide_file_name: str
    website_url: str
    total_guide_images: int
    total_website_images: int
    passed_count: int
    warning_count: int
    failed_count: int
    results: list[ComparisonResult]

    @property
    def failed_results(self) -> list[ComparisonResult]: ...
    @property
    def warning_results(self) -> list[ComparisonResult]: ...
    @property
    def passed_results(self) -> list[ComparisonResult]: ...
```

---

## Services

### GuideSpecParser (`app/services/guide_spec_parser.py`)

Parses PDF text to extract image specs.

**Key logic:**
1. Iterate through `GuideEvidence.pages`
2. For each page, find image specs in text using regex:
   ```
   Pattern: "(?P<name>.+?)\s*\|\s*Dimensions:\s*(?P<w>\d+)\s*[xX×]\s*(?P<h>\d+)\s*px\s*\|\s*Format:\s*(?P<fmt>\w+)"
   ```
3. Handle special cases:
   - "Same as above" → inherit from previous
   - Multiple specs per page
   - Variations in dimension formatting (1280 X 720, 1280x720, etc.)
4. Return `list[GuideImageSpec]`

**Regex patterns to handle:**
```
- "Width 1280 X Height 720 px"
- "1280 X 720 px"
- "1280 x 720"
- Dimensions: 1920 X 1080 px
```

### ImageMatcher (`app/services/image_matcher.py`)

Matches guide specs → website images.

**Matching strategy (in priority order):**

1. **Exact label match**: If guide image name appears in website image alt/src
2. **Dimension match (fallback)**: If exact label fails, match by W×H (±5px tolerance for rounding)
3. **Best candidate (no perfect match)**: If multiple candidates exist with similar dimensions, pick closest and flag as AMBIGUOUS

**Key methods:**
```python
class ImageMatcher:
    def match(self, guide_specs: list[GuideImageSpec], crawl_result: CrawlResult) -> list[tuple[GuideImageSpec, ImageEvidence | None, bool]]:
        # Returns: (spec, matched_image, is_ambiguous)
```

### UIComparisonEngine (`app/services/ui_comparison_engine.py`)

Orchestrates the comparison.

```python
class UIComparisonEngine:
    def compare(self, guide_evidence: GuideEvidence | None, crawl_result: CrawlResult) -> ComparisonReport:
        if guide_evidence:
            # Full comparison with dimension/format checks
            specs = GuideSpecParser().parse(guide_evidence)
            matches = ImageMatcher().match(specs, crawl_result)
            results = [self._evaluate_match(spec, image, ambiguous) for spec, image, ambiguous in matches]
            results.extend(self._check_untracked_images(crawl_result, matched))
        else:
            # No guide - basic health check only
            results = self._check_all_images_health(crawl_result)

        return ComparisonReport(results=results)
```

---

## Configuration Changes

### `config/websites.yaml` - New optional field

```yaml
websites:
  - name: Texas Chicken Iraq
    country: Iraq
    base_url: https://iraq.texaschicken.com/
    max_pages: 12
    max_links_to_check: 150  # NEW - optional, defaults to 80 if not set
```

### WebsiteHealthAuditor

Accept configurable max links from website config:

```python
def __init__(self, max_links: int = 80):
    self.max_links_to_check = max_links
```

---

## Behavior Summary

| Scenario | Result |
|----------|--------|
| Guide uploaded + Website has image matching guide spec | Check exact dimensions + format |
| Guide uploaded + Image missing on website | CRITICAL - Missing image |
| Guide uploaded + Multiple website images match spec | WARNING - Ambiguous match |
| Guide uploaded + Untracked website image broken | WARNING - Untracked broken |
| Guide uploaded + Untracked website image healthy | No report (ignore) |
| No guide uploaded | Check all images: broken = CRITICAL, missing alt = WARNING |
| Broken links | Already implemented via Functional checks |

---

## Severity Definitions

| Severity | When Triggered |
|----------|----------------|
| **CRITICAL** | Missing image, dimension mismatch, format mismatch, broken image |
| **WARNING** | Ambiguous match, untracked broken, missing alt text |
| **PASSED** | All checks pass |

---

## Report Output Structure

```json
{
  "guide_file_name": "Texas-Church's Chicken - Digital Assets Guide...",
  "website_url": "https://iraq.texaschicken.com/",
  "total_guide_images": 45,
  "total_website_images": 127,
  "passed_count": 38,
  "warning_count": 5,
  "failed_count": 2,
  "results": [
    {
      "guide_spec": { "image_name": "Hero Banner", "width": 1280, "height": 720, "format": "PNG" },
      "matched_website_image": { "src": "...", "width": 1280, "height": 720 },
      "issue": "PASSED",
      "severity": "Passed",
      "page_url": "https://iraq.texaschicken.com/",
      "expected_dimensions": [1280, 720],
      "actual_dimensions": [1280, 720],
      "details": "Image matches guide spec"
    },
    {
      "guide_spec": { "image_name": "Footer Logo", "width": 200, "height": 80, "format": "PNG" },
      "matched_website_image": null,
      "issue": "MISSING_IMAGE",
      "severity": "Critical",
      "page_url": null,
      "expected_dimensions": [200, 80],
      "actual_dimensions": null,
      "screenshot_path": null,
      "details": "Footer Logo not found on any crawled page"
    }
  ]
}
```

---

## Streamlit UI Additions

New section `## UI Comparison Report` appearing after `## Audit Check Status`:

1. **Summary metrics** - 5 columns: Guide Images, Website Images, Passed, Warnings, Failed
2. **Failed items** - Expandable cards with screenshot + issue details
3. **Warning items** - Collapsible list with issue summaries
4. **Passed items** - Dataframe summary

---

## Tests to Write

1. `test_guide_spec_parser.py` - Test dimension parsing (1280 X 720, 1280x720, etc.)
2. `test_image_matcher.py` - Test exact match, dimension fallback, ambiguity detection
3. `test_ui_comparison_engine.py` - Test with/without guide, result categorization
4. `test_comparison_result_model.py` - Test severity/issue enums

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Guide PDF has no text specs | Warn user "No image specs found in PDF", skip comparison |
| No guide uploaded but UI_COMPARISON selected | Error message "Upload brand guide PDF to run UI comparison" |
| Website image matches multiple guide specs | Flag as AMBIGUOUS, severity=Warning, pick best match |
| Guide image not found on website | Issue=MISSING_IMAGE, severity=Critical |
| Guide image found but wrong dimensions | Issue=DIMENSION_MISMATCH, severity=Critical |
| Guide image found but wrong format | Issue=FORMAT_MISMATCH, severity=Critical |
| Untracked website image is broken | Issue=UNTRACKED_BROKEN, severity=Warning |
| No website images at all | All guide images → MISSING_IMAGE (Critical) |

---

## Implementation Steps (Order)

1. **Create models** - `GuideImageSpec`, `ComparisonIssue`, `ComparisonSeverity`, `ComparisonResult`, `ComparisonReport`

2. **Create `GuideSpecParser`** - Parse PDF text to extract specs using regex. Test with extracted images from `reports/guide/`

3. **Create `ImageMatcher`** - Implement label + dimension matching logic with ambiguity detection

4. **Create `UIComparisonEngine`** - Orchestrate parsing + matching + result building

5. **Modify `test_result.py`** - Add `UI_COMPARISON` CheckType

6. **Modify `website_health_auditor.py`** - Import and call `UIComparisonEngine` when `UI_COMPARISON` in test_types, make MAX_LINKS configurable

7. **Modify `websites.yaml`** - Add `max_links_to_check` optional field

8. **Modify `streamlit_app.py`** - Add `_render_comparison_report()` and wire into main flow

9. **Write tests** - `test_guide_spec_parser.py`, `test_image_matcher.py`, `test_ui_comparison_engine.py`

10. **Run lint + typecheck**