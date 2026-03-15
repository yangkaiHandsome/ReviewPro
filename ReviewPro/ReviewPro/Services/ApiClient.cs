using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.IO;
using System.Text;
using System.Text.Json;
using ReviewPro.Models;

namespace ReviewPro.Services;

public sealed class ApiClient : IDisposable
{
    public sealed class ApiException : Exception
    {
        public System.Net.HttpStatusCode StatusCode { get; }
        public string ResponseBody { get; }

        public ApiException(System.Net.HttpStatusCode statusCode, string responseBody)
            : base($"API {statusCode}: {responseBody}")
        {
            StatusCode = statusCode;
            ResponseBody = responseBody;
        }
    }

    private readonly HttpClient _http;
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };
    private string _baseUrl;

    public ApiClient(string baseUrl)
    {
        _baseUrl = Normalize(baseUrl);
        _http = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(60),
        };
    }

    public void SetBaseUrl(string baseUrl)
    {
        _baseUrl = Normalize(baseUrl);
    }

    public async Task<bool> CheckHealthAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            using HttpResponseMessage response = await _http.GetAsync(Build("/health"), cancellationToken);
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    public Task<List<StrategyDto>> GetStrategiesAsync(CancellationToken cancellationToken = default) =>
        GetJsonAsync<List<StrategyDto>>("/strategies", cancellationToken);

    public Task<StrategyDto> CreateStrategyAsync(
        StrategyUpsertRequest request,
        CancellationToken cancellationToken = default) =>
        PostJsonAsync<StrategyDto>("/strategies", request, cancellationToken);

    public Task<StrategyDto> UpdateStrategyAsync(
        string strategyId,
        StrategyUpsertRequest request,
        CancellationToken cancellationToken = default) =>
        PutJsonAsync<StrategyDto>($"/strategies/{strategyId}", request, cancellationToken);

    public async Task DeleteStrategyAsync(string strategyId, CancellationToken cancellationToken = default)
    {
        using HttpResponseMessage response = await _http.DeleteAsync(Build($"/strategies/{strategyId}"), cancellationToken);
        await EnsureSuccessAsync(response);
    }

    public Task<List<DocumentDto>> GetDocumentsAsync(CancellationToken cancellationToken = default) =>
        GetJsonAsync<List<DocumentDto>>("/documents", cancellationToken);

    public async Task DeleteDocumentAsync(string docId, CancellationToken cancellationToken = default)
    {
        using HttpResponseMessage response = await _http.DeleteAsync(Build($"/documents/{docId}"), cancellationToken);
        await EnsureSuccessAsync(response);
    }

    public Task<List<PageMetaDto>> GetDocumentPagesAsync(
        string docId,
        CancellationToken cancellationToken = default) =>
        GetJsonAsync<List<PageMetaDto>>($"/documents/{docId}/pages", cancellationToken);

    public async Task<UploadResponseDto> UploadDocumentAsync(string filePath, CancellationToken cancellationToken = default)
    {
        await using FileStream stream = File.OpenRead(filePath);
        using StreamContent fileContent = new(stream);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        using MultipartFormDataContent form = new();
        form.Add(fileContent, "file", Path.GetFileName(filePath));
        using HttpResponseMessage response = await _http.PostAsync(Build("/documents/upload"), form, cancellationToken);
        await EnsureSuccessAsync(response);
        UploadResponseDto? payload = await response.Content.ReadFromJsonAsync<UploadResponseDto>(_jsonOptions, cancellationToken);
        return payload ?? throw new InvalidOperationException("Invalid upload response.");
    }

    public async Task<byte[]> GetPageImageAsync(
        string docId,
        int pageNumber,
        int dpi = 150,
        CancellationToken cancellationToken = default)
    {
        using HttpResponseMessage response = await _http.GetAsync(
            Build($"/documents/{docId}/page/{pageNumber}/image?dpi={dpi}"),
            cancellationToken);
        await EnsureSuccessAsync(response);
        return await response.Content.ReadAsByteArrayAsync(cancellationToken);
    }

    public Task<AuditSubmitResponseDto> SubmitAuditAsync(
        string docId,
        string strategyId,
        CancellationToken cancellationToken = default) =>
        PostJsonAsync<AuditSubmitResponseDto>(
            "/audit",
            new { doc_id = docId, strategy_id = strategyId },
            cancellationToken);

    public Task<AuditSubmitResponseDto> RetryAuditAsync(
        string docId,
        CancellationToken cancellationToken = default) =>
        PostJsonAsync<AuditSubmitResponseDto>($"/audit/{docId}/retry", new { }, cancellationToken);

    public Task<AuditJobDto> GetAuditJobAsync(string jobId, CancellationToken cancellationToken = default) =>
        GetJsonAsync<AuditJobDto>($"/audit/job/{jobId}", cancellationToken);

    public Task<AuditJobDto> GetLatestDocumentAuditAsync(string docId, CancellationToken cancellationToken = default) =>
        GetJsonAsync<AuditJobDto>($"/audit/{docId}", cancellationToken);

    private static string Normalize(string baseUrl)
    {
        string cleaned = baseUrl.Trim().TrimEnd('/');
        return cleaned;
    }

    private Uri Build(string path) => new($"{_baseUrl}{path}");

    private async Task<T> GetJsonAsync<T>(string path, CancellationToken cancellationToken)
    {
        using HttpResponseMessage response = await _http.GetAsync(Build(path), cancellationToken);
        await EnsureSuccessAsync(response);
        T? payload = await response.Content.ReadFromJsonAsync<T>(_jsonOptions, cancellationToken);
        return payload ?? throw new InvalidOperationException("Empty response payload.");
    }

    private async Task<T> PostJsonAsync<T>(string path, object request, CancellationToken cancellationToken)
    {
        using HttpResponseMessage response = await _http.PostAsJsonAsync(
            Build(path),
            request,
            _jsonOptions,
            cancellationToken);
        await EnsureSuccessAsync(response);
        T? payload = await response.Content.ReadFromJsonAsync<T>(_jsonOptions, cancellationToken);
        return payload ?? throw new InvalidOperationException("Empty response payload.");
    }

    private async Task<T> PutJsonAsync<T>(string path, object request, CancellationToken cancellationToken)
    {
        string json = JsonSerializer.Serialize(request, _jsonOptions);
        using HttpRequestMessage message = new(HttpMethod.Put, Build(path))
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json"),
        };
        using HttpResponseMessage response = await _http.SendAsync(message, cancellationToken);
        await EnsureSuccessAsync(response);
        T? payload = await response.Content.ReadFromJsonAsync<T>(_jsonOptions, cancellationToken);
        return payload ?? throw new InvalidOperationException("Empty response payload.");
    }

    private static async Task EnsureSuccessAsync(HttpResponseMessage response)
    {
        if (response.IsSuccessStatusCode)
        {
            return;
        }

        string message = await response.Content.ReadAsStringAsync();
        throw new ApiException(response.StatusCode, message);
    }

    public void Dispose()
    {
        _http.Dispose();
    }
}
