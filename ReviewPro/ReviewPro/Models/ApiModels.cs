using System.Text.Json.Serialization;

namespace ReviewPro.Models;

public sealed class RuleDto
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; set; } = string.Empty;

    [JsonPropertyName("severity")]
    public string Severity { get; set; } = "medium";

    [JsonPropertyName("is_required")]
    public bool IsRequired { get; set; } = true;
}

public sealed class StrategyDto
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("created_at")]
    public DateTime CreatedAt { get; set; }

    [JsonPropertyName("rules")]
    public List<RuleDto> Rules { get; set; } = new();

    public string Summary => $"{Name} · {Rules.Count} rules";
}

public sealed class StrategyUpsertRequest
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("rules")]
    public List<RuleDto> Rules { get; set; } = new();
}

public sealed class DocumentDto
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("filename")]
    public string Filename { get; set; } = string.Empty;

    [JsonPropertyName("mime_type")]
    public string MimeType { get; set; } = string.Empty;

    [JsonPropertyName("page_count")]
    public int PageCount { get; set; }

    [JsonPropertyName("doc_type")]
    public string DocType { get; set; } = string.Empty;

    [JsonPropertyName("upload_time")]
    public DateTime UploadTime { get; set; }

    public string Summary => $"{Filename} · {PageCount} pages · {DocType}";
}

public sealed class UploadResponseDto
{
    [JsonPropertyName("doc_id")]
    public string DocId { get; set; } = string.Empty;

    [JsonPropertyName("filename")]
    public string Filename { get; set; } = string.Empty;

    [JsonPropertyName("page_count")]
    public int PageCount { get; set; }

    [JsonPropertyName("doc_type")]
    public string DocType { get; set; } = string.Empty;
}

public sealed class PageMetaDto
{
    [JsonPropertyName("page_number")]
    public int PageNumber { get; set; }

    [JsonPropertyName("has_text")]
    public bool HasText { get; set; }

    [JsonPropertyName("text_preview")]
    public string TextPreview { get; set; } = string.Empty;

    [JsonPropertyName("image_density")]
    public double ImageDensity { get; set; }

    [JsonPropertyName("page_width")]
    public double PageWidth { get; set; }

    [JsonPropertyName("page_height")]
    public double PageHeight { get; set; }

    [JsonPropertyName("is_toc_like")]
    public bool IsTocLike { get; set; }

    [JsonPropertyName("likely_drawing")]
    public bool LikelyDrawing { get; set; }
}

public sealed class AuditSubmitResponseDto
{
    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("progress")]
    public double Progress { get; set; }
}

public sealed class ReviewPlanPageDto
{
    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("depth")]
    public string Depth { get; set; } = string.Empty;

    [JsonPropertyName("reason")]
    public string Reason { get; set; } = string.Empty;
}

public sealed class ReviewPlanDto
{
    [JsonPropertyName("page_budget")]
    public int PageBudget { get; set; }

    [JsonPropertyName("selected_pages")]
    public List<ReviewPlanPageDto> SelectedPages { get; set; } = new();

    [JsonPropertyName("coverage_warnings")]
    public List<string> CoverageWarnings { get; set; } = new();

    [JsonPropertyName("notes")]
    public List<string> Notes { get; set; } = new();
}

public sealed class AuditResultDto
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = string.Empty;

    [JsonPropertyName("rule_id")]
    public string RuleId { get; set; } = string.Empty;

    [JsonPropertyName("page")]
    public int Page { get; set; }

    [JsonPropertyName("bbox")]
    public List<double> Bbox { get; set; } = new();

    [JsonPropertyName("content")]
    public string Content { get; set; } = string.Empty;

    [JsonPropertyName("suggestion")]
    public string Suggestion { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("severity")]
    public string Severity { get; set; } = string.Empty;

    public string Badge => $"{Status.ToUpperInvariant()} · P{Page}";
    public string StatusLabel => Status.ToUpperInvariant();
}

public sealed class AuditJobDto
{
    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = string.Empty;

    [JsonPropertyName("doc_id")]
    public string DocId { get; set; } = string.Empty;

    [JsonPropertyName("strategy_id")]
    public string StrategyId { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("progress")]
    public double Progress { get; set; }

    [JsonPropertyName("error_message")]
    public string? ErrorMessage { get; set; }

    [JsonPropertyName("review_plan")]
    public ReviewPlanDto? ReviewPlan { get; set; }

    [JsonPropertyName("visited_pages")]
    public List<int> VisitedPages { get; set; } = new();

    [JsonPropertyName("audit_log")]
    public List<string> AuditLog { get; set; } = new();

    [JsonPropertyName("results")]
    public List<AuditResultDto> Results { get; set; } = new();
}

public sealed class RuleEditorModel
{
    public string Id { get; set; } = string.Empty;

    public string Title { get; set; } = string.Empty;

    public string Description { get; set; } = string.Empty;

    public string Severity { get; set; } = "medium";

    public bool IsRequired { get; set; } = true;
}
