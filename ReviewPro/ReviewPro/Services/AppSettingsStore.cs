using System.IO;
using System.Text.Json;

namespace ReviewPro.Services;

public sealed class AppSettingsStore
{
    private const string DefaultBackendUrl = "http://127.0.0.1:8000/api";

    private readonly string _settingsPath;

    public AppSettingsStore()
    {
        string appDataDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "ReviewPro");
        Directory.CreateDirectory(appDataDirectory);
        _settingsPath = Path.Combine(appDataDirectory, "settings.json");
    }

    public string LoadBackendUrl()
    {
        try
        {
            if (!File.Exists(_settingsPath))
            {
                return DefaultBackendUrl;
            }

            string json = File.ReadAllText(_settingsPath);
            AppSettingsModel? settings = JsonSerializer.Deserialize<AppSettingsModel>(json);
            return string.IsNullOrWhiteSpace(settings?.BackendUrl) ? DefaultBackendUrl : settings.BackendUrl;
        }
        catch
        {
            return DefaultBackendUrl;
        }
    }

    public void SaveBackendUrl(string backendUrl)
    {
        AppSettingsModel settings = new()
        {
            BackendUrl = backendUrl,
        };
        string json = JsonSerializer.Serialize(settings, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText(_settingsPath, json);
    }

    private sealed class AppSettingsModel
    {
        public string BackendUrl { get; set; } = DefaultBackendUrl;
    }
}
