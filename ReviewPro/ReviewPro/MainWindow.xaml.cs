using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Net;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;
using System.Windows.Threading;
using ReviewPro.Models;
using ReviewPro.Services;
using Microsoft.Win32;

namespace ReviewPro;

public partial class MainWindow : Window
{
    private const string DefaultBackendUrl = "http://127.0.0.1:8000/api";

    private readonly ApiClient _apiClient;
    private readonly AppSettingsStore _settingsStore;
    private readonly ObservableCollection<DocumentDto> _documents = new();
    private readonly ObservableCollection<StrategyDto> _strategies = new();
    private readonly ObservableCollection<AuditResultDto> _auditResults = new();
    private readonly ObservableCollection<RuleEditorModel> _strategyRules = new();
    private readonly Dictionary<string, AuditJobDto> _auditJobsByDocId = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> _runningAuditJobsByDocId = new(StringComparer.Ordinal);

    private readonly List<string> _severityOptions = new() { "low", "medium", "high" };

    private List<PageMetaDto> _currentPages = new();
    private string? _editingStrategyId;
    private string? _displayedAuditDocId;
    private int _currentPage = 1;
    private BitmapImage? _currentBitmap;
    private CancellationTokenSource? _pollCancellation;
    private Task? _pollLoopTask;
    private AuditResultDto? _pendingFocusResult;
    private string? _focusedAuditResultId;
    private double _zoomFactor = 0.5;
    private string _backendBaseUrl = DefaultBackendUrl;

    public IReadOnlyList<string> SeverityOptions => _severityOptions;

    public MainWindow()
    {
        InitializeComponent();
        DataContext = this;

        _settingsStore = new AppSettingsStore();
        _backendBaseUrl = _settingsStore.LoadBackendUrl();
        _apiClient = new ApiClient(_backendBaseUrl);

        DocumentsListBox.ItemsSource = _documents;
        StrategiesListBox.ItemsSource = _strategies;
        AuditStrategyComboBox.ItemsSource = _strategies;
        AuditResultsListBox.ItemsSource = _auditResults;
        RulesDataGrid.ItemsSource = _strategyRules;
        UpdatePreviewZoom();
    }

    private async void Window_Loaded(object sender, RoutedEventArgs e)
    {
        try
        {
            await RefreshAllAsync();
        }
        catch (Exception ex)
        {
            ShowError("Initialize App", ex);
        }
    }

    private void Window_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        _pollCancellation?.Cancel();
        _apiClient.Dispose();
    }

    private async Task RefreshAllAsync()
    {
        bool isBackendAvailable = await HealthCheckAsync();
        if (!isBackendAvailable)
        {
            ClearFrontendData();
            return;
        }

        await LoadDocumentsAsync();
        await LoadStrategiesAsync();
    }

    private async Task<bool> HealthCheckAsync()
    {
        bool ok = await _apiClient.CheckHealthAsync();
        BackendStatusTextBlock.Text = ok ? "Online" : "Offline";
        BackendStatusTextBlock.Foreground = ok
            ? new SolidColorBrush(Color.FromRgb(22, 120, 74))
            : new SolidColorBrush(Color.FromRgb(138, 47, 47));
        BackendHintTextBlock.Text = ok
            ? $"Connected to {_backendBaseUrl}"
            : "Unable to reach server. Open Settings to update the backend address.";
        return ok;
    }

    private async Task LoadDocumentsAsync(string? preferredDocId = null)
    {
        List<DocumentDto> docs = await _apiClient.GetDocumentsAsync();
        ReplaceCollection(_documents, docs);

        if (_documents.Count == 0)
        {
            _currentPages = new List<PageMetaDto>();
            _currentPage = 1;
            ClearDisplayedAuditState();
            ClearPreview();
            return;
        }

        DocumentDto? selected = null;
        if (!string.IsNullOrWhiteSpace(preferredDocId))
        {
            selected = _documents.FirstOrDefault(d => d.Id == preferredDocId);
        }
        if (selected is null && DocumentsListBox.SelectedItem is DocumentDto current)
        {
            selected = _documents.FirstOrDefault(d => d.Id == current.Id);
        }
        selected ??= _documents[0];
        DocumentsListBox.SelectedItem = selected;
    }

    private async Task LoadStrategiesAsync(string? preferredStrategyId = null)
    {
        List<StrategyDto> strategies = await _apiClient.GetStrategiesAsync();
        ReplaceCollection(_strategies, strategies);

        if (_strategies.Count == 0)
        {
            _editingStrategyId = null;
            _strategyRules.Clear();
            StrategyNameTextBox.Text = string.Empty;
            return;
        }

        StrategyDto? preferred = null;
        if (!string.IsNullOrWhiteSpace(preferredStrategyId))
        {
            preferred = _strategies.FirstOrDefault(s => s.Id == preferredStrategyId);
        }

        if (preferred is null && AuditStrategyComboBox.SelectedItem is StrategyDto currentAudit)
        {
            preferred = _strategies.FirstOrDefault(s => s.Id == currentAudit.Id);
        }

        preferred ??= _strategies[0];
        AuditStrategyComboBox.SelectedItem = preferred;

        if (StrategiesListBox.SelectedItem is not StrategyDto currentEditor ||
            _strategies.All(s => s.Id != currentEditor.Id))
        {
            StrategiesListBox.SelectedItem = preferred;
        }
    }

    private async Task LoadSelectedDocumentPagesAsync()
    {
        DocumentDto? doc = DocumentsListBox.SelectedItem as DocumentDto;
        if (doc is null)
        {
            _currentPages = new List<PageMetaDto>();
            ClearDisplayedAuditState();
            ClearPreview();
            return;
        }

        _currentPages = await _apiClient.GetDocumentPagesAsync(doc.Id);
        _currentPage = _currentPages.FirstOrDefault()?.PageNumber ?? 1;
        await LoadLatestAuditForSelectedDocumentAsync();
        await LoadCurrentPageImageAsync();
    }

    private async Task LoadLatestAuditForSelectedDocumentAsync()
    {
        DocumentDto? doc = DocumentsListBox.SelectedItem as DocumentDto;
        if (doc is null)
        {
            ClearDisplayedAuditState();
            return;
        }

        try
        {
            AuditJobDto job = await _apiClient.GetLatestDocumentAuditAsync(doc.Id);
            CacheAuditJob(job);
            ApplyAuditJob(job);

            if (!string.IsNullOrWhiteSpace(job.StrategyId))
            {
                StrategyDto? strategy = _strategies.FirstOrDefault(s => s.Id == job.StrategyId);
                if (strategy is not null)
                {
                    AuditStrategyComboBox.SelectedItem = strategy;
                }
            }

            if (job.Status.Equals("pending", StringComparison.OrdinalIgnoreCase) ||
                job.Status.Equals("running", StringComparison.OrdinalIgnoreCase))
            {
                TrackRunningAudit(job);
            }
        }
        catch (ApiClient.ApiException ex) when (ex.StatusCode == HttpStatusCode.NotFound)
        {
            _auditJobsByDocId.Remove(doc.Id);
            _runningAuditJobsByDocId.Remove(doc.Id);
            DisplayAuditForDocument(doc.Id);
        }
    }

    private async Task LoadCurrentPageImageAsync()
    {
        DocumentDto? doc = DocumentsListBox.SelectedItem as DocumentDto;
        if (doc is null || _currentPages.Count == 0)
        {
            ClearPreview();
            return;
        }

        _currentPage = Math.Max(1, Math.Min(_currentPage, _currentPages.Count));
        byte[] imageBytes = await _apiClient.GetPageImageAsync(doc.Id, _currentPage);

        using MemoryStream stream = new(imageBytes);
        BitmapImage bitmap = new();
        bitmap.BeginInit();
        bitmap.CacheOption = BitmapCacheOption.OnLoad;
        bitmap.StreamSource = stream;
        bitmap.EndInit();
        bitmap.Freeze();

        _currentBitmap = bitmap;

        PagePreviewImage.Source = bitmap;
        PagePreviewImage.Width = bitmap.PixelWidth;
        PagePreviewImage.Height = bitmap.PixelHeight;
        PagePreviewCanvas.Width = bitmap.PixelWidth;
        PagePreviewCanvas.Height = bitmap.PixelHeight;
        PreviewGrid.Width = bitmap.PixelWidth;
        PreviewGrid.Height = bitmap.PixelHeight;

        CurrentPageTextBlock.Text = $"Page {_currentPage} / {_currentPages.Count}";
        DrawAnnotations();
        if (_pendingFocusResult is not null && _pendingFocusResult.Page == _currentPage)
        {
            FocusPreviewOnResult(_pendingFocusResult);
        }
    }

    private void DrawAnnotations()
    {
        PagePreviewCanvas.Children.Clear();
        if (_currentBitmap is null)
        {
            return;
        }

        PageMetaDto? meta = _currentPages.FirstOrDefault(p => p.PageNumber == _currentPage);
        if (meta is null)
        {
            return;
        }

        double scaleX = meta.PageWidth > 0 ? _currentBitmap.PixelWidth / meta.PageWidth : 1.0;
        double scaleY = meta.PageHeight > 0 ? _currentBitmap.PixelHeight / meta.PageHeight : 1.0;

        foreach (AuditResultDto result in _auditResults.Where(r => r.Page == _currentPage))
        {
            if (result.Bbox.Count != 4)
            {
                continue;
            }

            double x = result.Bbox[0] * scaleX;
            double y = result.Bbox[1] * scaleY;
            double width = Math.Max(8, (result.Bbox[2] - result.Bbox[0]) * scaleX);
            double height = Math.Max(8, (result.Bbox[3] - result.Bbox[1]) * scaleY);
            bool isFocused = string.Equals(result.Id, _focusedAuditResultId, StringComparison.Ordinal);

            Rectangle rect = new()
            {
                Width = width,
                Height = height,
                StrokeThickness = isFocused ? 4 : 2,
                Stroke = result.Status.Equals("fail", StringComparison.OrdinalIgnoreCase)
                    ? (isFocused ? Brushes.OrangeRed : Brushes.IndianRed)
                    : Brushes.SeaGreen,
                Fill = isFocused
                    ? new SolidColorBrush(Color.FromArgb(70, 255, 196, 0))
                    : new SolidColorBrush(Color.FromArgb(30, 25, 90, 150)),
                RadiusX = 3,
                RadiusY = 3,
                ToolTip = $"{result.RuleId}: {result.Content}",
            };
            Canvas.SetLeft(rect, x);
            Canvas.SetTop(rect, y);
            PagePreviewCanvas.Children.Add(rect);

            Border badge = new()
            {
                Background = isFocused
                    ? new SolidColorBrush(Color.FromRgb(214, 140, 24))
                    : result.Status.Equals("fail", StringComparison.OrdinalIgnoreCase)
                        ? new SolidColorBrush(Color.FromRgb(178, 53, 64))
                        : new SolidColorBrush(Color.FromRgb(32, 124, 90)),
                CornerRadius = new CornerRadius(4),
                Padding = new Thickness(6, 2, 6, 2),
                Child = new TextBlock
                {
                    Foreground = Brushes.White,
                    FontSize = 11,
                    FontFamily = new FontFamily("Bahnschrift"),
                    Text = result.RuleId,
                },
            };
            Canvas.SetLeft(badge, x);
            Canvas.SetTop(badge, Math.Max(0, y - 22));
            PagePreviewCanvas.Children.Add(badge);
        }
    }

    private void ClearPreview()
    {
        _currentBitmap = null;
        _pendingFocusResult = null;
        _focusedAuditResultId = null;
        PagePreviewImage.Source = null;
        PagePreviewCanvas.Children.Clear();
        PagePreviewCanvas.Width = 0;
        PagePreviewCanvas.Height = 0;
        PreviewGrid.Width = double.NaN;
        PreviewGrid.Height = double.NaN;
        CurrentPageTextBlock.Text = "Page - / -";
    }

    private void UpdatePreviewZoom()
    {
        PreviewScaleTransform.ScaleX = _zoomFactor;
        PreviewScaleTransform.ScaleY = _zoomFactor;
        ZoomTextBlock.Text = $"{_zoomFactor * 100:0}%";
    }

    private void SetZoom(double zoomFactor)
    {
        _zoomFactor = Math.Clamp(zoomFactor, 0.5, 3.0);
        UpdatePreviewZoom();

        if (_pendingFocusResult is not null && _pendingFocusResult.Page == _currentPage)
        {
            FocusPreviewOnResult(_pendingFocusResult);
        }
        else if (AuditResultsListBox.SelectedItem is AuditResultDto selected && selected.Page == _currentPage)
        {
            _pendingFocusResult = selected;
            FocusPreviewOnResult(selected);
        }
    }

    private void CacheAuditJob(AuditJobDto job)
    {
        _auditJobsByDocId[job.DocId] = job;
    }

    private void TrackRunningAudit(AuditJobDto job)
    {
        CacheAuditJob(job);
        _runningAuditJobsByDocId[job.DocId] = job.JobId;
        EnsureAuditPollingLoop();
    }

    private void EnsureAuditPollingLoop()
    {
        if (_pollLoopTask is { IsCompleted: false })
        {
            return;
        }

        _pollCancellation ??= new CancellationTokenSource();
        _pollLoopTask = PollRunningAuditsLoopAsync(_pollCancellation.Token);
    }

    private async Task PollRunningAuditsLoopAsync(CancellationToken token)
    {
        try
        {
            while (!token.IsCancellationRequested)
            {
                KeyValuePair<string, string>[] runningJobs = _runningAuditJobsByDocId.ToArray();
                if (runningJobs.Length == 0)
                {
                    break;
                }

                foreach (KeyValuePair<string, string> runningJob in runningJobs)
                {
                    AuditJobDto job;
                    try
                    {
                        job = await _apiClient.GetAuditJobAsync(runningJob.Value, token);
                    }
                    catch (ApiClient.ApiException ex) when (ex.StatusCode == HttpStatusCode.NotFound)
                    {
                        _runningAuditJobsByDocId.Remove(runningJob.Key);
                        continue;
                    }

                    CacheAuditJob(job);
                    if (job.Status.Equals("completed", StringComparison.OrdinalIgnoreCase) ||
                        job.Status.Equals("failed", StringComparison.OrdinalIgnoreCase))
                    {
                        _runningAuditJobsByDocId.Remove(job.DocId);
                    }

                    if (DocumentsListBox.SelectedItem is DocumentDto selectedDoc &&
                        string.Equals(selectedDoc.Id, job.DocId, StringComparison.Ordinal))
                    {
                        ApplyAuditJob(job);
                    }
                }

                await Task.Delay(1200, token);
            }
        }
        catch (OperationCanceledException)
        {
        }
        finally
        {
            _pollLoopTask = null;
        }
    }

    private void ApplyAuditJob(AuditJobDto job)
    {
        CacheAuditJob(job);
        _displayedAuditDocId = job.DocId;
        AuditProgressBar.Value = Math.Clamp(job.Progress, 0, 100);
        AuditStatusTextBlock.Text = string.IsNullOrWhiteSpace(job.ErrorMessage)
            ? $"{job.Status.ToUpperInvariant()} · {job.Progress:0}%"
            : $"{job.Status.ToUpperInvariant()} · {job.ErrorMessage}";

        ReplaceCollection(_auditResults, job.Results);
        DrawAnnotations();
    }

    private void DisplayAuditForDocument(string docId)
    {
        if (_auditJobsByDocId.TryGetValue(docId, out AuditJobDto? job))
        {
            ApplyAuditJob(job);
            return;
        }

        ClearDisplayedAuditState();
    }

    private void ClearDisplayedAuditState()
    {
        _displayedAuditDocId = null;
        _auditResults.Clear();
        AuditResultsListBox.SelectedItem = null;
        AuditStatusTextBlock.Text = "Idle";
        AuditProgressBar.Value = 0;
        _pendingFocusResult = null;
        _focusedAuditResultId = null;
        DrawAnnotations();
    }

    private void ClearFrontendData()
    {
        _documents.Clear();
        _strategies.Clear();
        _strategyRules.Clear();
        _auditJobsByDocId.Clear();
        _runningAuditJobsByDocId.Clear();
        DocumentsListBox.SelectedItem = null;
        StrategiesListBox.SelectedItem = null;
        AuditStrategyComboBox.SelectedItem = null;
        StrategyNameTextBox.Text = string.Empty;
        _editingStrategyId = null;
        _currentPages = new List<PageMetaDto>();
        _currentPage = 1;
        ClearDisplayedAuditState();
        ClearPreview();
    }

    private StrategyUpsertRequest BuildStrategyRequestFromEditor()
    {
        return new StrategyUpsertRequest
        {
            Name = StrategyNameTextBox.Text.Trim(),
            Rules = _strategyRules.Select(rule => new RuleDto
            {
                Id = string.IsNullOrWhiteSpace(rule.Id) ? "R000" : rule.Id.Trim(),
                Title = rule.Title.Trim(),
                Description = rule.Description.Trim(),
                Severity = string.IsNullOrWhiteSpace(rule.Severity) ? "medium" : rule.Severity.Trim(),
                IsRequired = rule.IsRequired,
            }).ToList(),
        };
    }

    private void LoadStrategyEditor(StrategyDto strategy)
    {
        _editingStrategyId = strategy.Id;
        StrategyNameTextBox.Text = strategy.Name;
        ReplaceCollection(
            _strategyRules,
            strategy.Rules.Select(rule => new RuleEditorModel
            {
                Id = rule.Id,
                Title = rule.Title,
                Description = rule.Description,
                Severity = rule.Severity,
                IsRequired = rule.IsRequired,
            }));
    }

    private void ClearStrategyEditor()
    {
        _editingStrategyId = null;
        StrategyNameTextBox.Text = string.Empty;
        _strategyRules.Clear();
    }

    private static void ReplaceCollection<T>(ObservableCollection<T> target, IEnumerable<T> source)
    {
        target.Clear();
        foreach (T item in source)
        {
            target.Add(item);
        }
    }

    private static void ShowError(string title, Exception ex)
    {
        MessageBox.Show(ex.Message, title, MessageBoxButton.OK, MessageBoxImage.Error);
    }

    private async void HealthCheckButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshAllAsync();
    }

    private async void SettingsButton_Click(object sender, RoutedEventArgs e)
    {
        Window dialog = BuildSettingsDialog();
        if (dialog.ShowDialog() != true)
        {
            return;
        }

        if (dialog.Tag is not TextBox backendUrlTextBox)
        {
            return;
        }

        try
        {
            string newBaseUrl = backendUrlTextBox.Text.Trim();
            _apiClient.SetBaseUrl(newBaseUrl);
            _backendBaseUrl = newBaseUrl;
            _settingsStore.SaveBackendUrl(newBaseUrl);
            await RefreshAllAsync();
        }
        catch (Exception ex)
        {
            ShowError("Apply Backend URL", ex);
        }
    }

    private Window BuildSettingsDialog()
    {
        Window dialog = new()
        {
            Title = "Settings",
            Owner = this,
            Width = 460,
            Height = 210,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            ResizeMode = ResizeMode.NoResize,
            Background = new SolidColorBrush(Color.FromRgb(243, 246, 250)),
        };

        Grid layout = new()
        {
            Margin = new Thickness(20),
        };
        layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        layout.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        TextBlock title = new()
        {
            Text = "Backend Settings",
            FontFamily = new FontFamily("Bahnschrift"),
            FontSize = 20,
            FontWeight = FontWeights.Bold,
            Foreground = new SolidColorBrush(Color.FromRgb(18, 58, 90)),
        };
        Grid.SetRow(title, 0);
        layout.Children.Add(title);

        StackPanel form = new()
        {
            Margin = new Thickness(0, 16, 0, 0),
        };
        TextBlock label = new()
        {
            Text = "Base URL",
            FontFamily = new FontFamily("Bahnschrift"),
            Margin = new Thickness(0, 0, 0, 6),
        };
        TextBox backendUrlTextBox = new()
        {
            Text = _backendBaseUrl,
            Height = 34,
            Padding = new Thickness(10, 6, 10, 6),
            BorderBrush = new SolidColorBrush(Color.FromRgb(185, 208, 234)),
        };
        form.Children.Add(label);
        form.Children.Add(backendUrlTextBox);
        Grid.SetRow(form, 1);
        layout.Children.Add(form);

        StackPanel actions = new()
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(0, 20, 0, 0),
        };
        Button cancelButton = new()
        {
            Content = "Cancel",
            MinWidth = 90,
            Padding = new Thickness(12, 6, 12, 6),
            Margin = new Thickness(0, 0, 8, 0),
        };
        cancelButton.Click += (_, _) => dialog.DialogResult = false;

        Button saveButton = new()
        {
            Content = "Save",
            MinWidth = 90,
            Padding = new Thickness(12, 6, 12, 6),
            Background = new SolidColorBrush(Color.FromRgb(14, 107, 168)),
            Foreground = Brushes.White,
            BorderBrush = new SolidColorBrush(Color.FromRgb(13, 94, 148)),
        };
        saveButton.Click += (_, _) => dialog.DialogResult = true;

        actions.Children.Add(cancelButton);
        actions.Children.Add(saveButton);
        Grid.SetRow(actions, 2);
        layout.Children.Add(actions);

        dialog.Tag = backendUrlTextBox;
        dialog.Content = layout;
        return dialog;
    }

    private async void RefreshDocumentsButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            await LoadDocumentsAsync();
        }
        catch (Exception ex)
        {
            ShowError("Refresh Documents", ex);
        }
    }

    private async void RefreshStrategiesButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            await LoadStrategiesAsync();
        }
        catch (Exception ex)
        {
            ShowError("Refresh Strategies", ex);
        }
    }

    private async void UploadButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            OpenFileDialog dialog = new()
            {
                Filter = "PDF/Image|*.pdf;*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff",
                Multiselect = false,
            };
            if (dialog.ShowDialog() != true)
            {
                return;
            }

            UploadResponseDto upload = await _apiClient.UploadDocumentAsync(dialog.FileName);
            await LoadDocumentsAsync(upload.DocId);
        }
        catch (Exception ex)
        {
            ShowError("Upload Document", ex);
        }
    }

    private async void DocumentsListBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        try
        {
            await LoadSelectedDocumentPagesAsync();
        }
        catch (Exception ex)
        {
            ShowError("Load Document", ex);
        }
    }

    private async void DeleteDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            if (DocumentsListBox.SelectedItem is not DocumentDto document)
            {
                MessageBox.Show("Select a document to remove.", "Remove Document", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            MessageBoxResult confirm = MessageBox.Show(
                $"Remove document '{document.Filename}'?",
                "Remove Document",
                MessageBoxButton.YesNo,
                MessageBoxImage.Question);
            if (confirm != MessageBoxResult.Yes)
            {
                return;
            }

            await _apiClient.DeleteDocumentAsync(document.Id);
            _auditJobsByDocId.Remove(document.Id);
            _runningAuditJobsByDocId.Remove(document.Id);
            ClearDisplayedAuditState();
            await LoadDocumentsAsync();
        }
        catch (Exception ex)
        {
            ShowError("Remove Document", ex);
        }
    }

    private async void PrevPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (_currentPages.Count == 0)
        {
            return;
        }
        _currentPage = Math.Max(1, _currentPage - 1);
        try
        {
            await LoadCurrentPageImageAsync();
        }
        catch (Exception ex)
        {
            ShowError("Previous Page", ex);
        }
    }

    private async void NextPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (_currentPages.Count == 0)
        {
            return;
        }
        _currentPage = Math.Min(_currentPages.Count, _currentPage + 1);
        try
        {
            await LoadCurrentPageImageAsync();
        }
        catch (Exception ex)
        {
            ShowError("Next Page", ex);
        }
    }

    private void ZoomOutButton_Click(object sender, RoutedEventArgs e)
    {
        SetZoom(_zoomFactor - 0.1);
    }

    private void ResetZoomButton_Click(object sender, RoutedEventArgs e)
    {
        SetZoom(1.0);
    }

    private void ZoomInButton_Click(object sender, RoutedEventArgs e)
    {
        SetZoom(_zoomFactor + 0.1);
    }

    private async void RunAuditButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            DocumentDto? doc = DocumentsListBox.SelectedItem as DocumentDto;
            StrategyDto? strategy = AuditStrategyComboBox.SelectedItem as StrategyDto;
            if (doc is null || strategy is null)
            {
                MessageBox.Show("Select both document and strategy first.", "Run Audit", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            AuditSubmitResponseDto submit = await _apiClient.SubmitAuditAsync(doc.Id, strategy.Id);
            AuditJobDto pendingJob = new()
            {
                JobId = submit.JobId,
                DocId = doc.Id,
                StrategyId = strategy.Id,
                Status = submit.Status,
                Progress = submit.Progress,
            };
            TrackRunningAudit(pendingJob);
            ApplyAuditJob(pendingJob);
        }
        catch (Exception ex)
        {
            ShowError("Run Audit", ex);
        }
    }

    private async void RetryAuditButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            DocumentDto? doc = DocumentsListBox.SelectedItem as DocumentDto;
            if (doc is null)
            {
                MessageBox.Show("Select a document first.", "Retry Audit", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            AuditSubmitResponseDto submit = await _apiClient.RetryAuditAsync(doc.Id);
            string strategyId = (AuditStrategyComboBox.SelectedItem as StrategyDto)?.Id ?? string.Empty;
            AuditJobDto pendingJob = new()
            {
                JobId = submit.JobId,
                DocId = doc.Id,
                StrategyId = strategyId,
                Status = submit.Status,
                Progress = submit.Progress,
            };
            TrackRunningAudit(pendingJob);
            ApplyAuditJob(pendingJob);
        }
        catch (Exception ex)
        {
            ShowError("Retry Audit", ex);
        }
    }

    private async void AuditResultsListBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        try
        {
            if (AuditResultsListBox.SelectedItem is not AuditResultDto result || _currentPages.Count == 0)
            {
                return;
            }
            _pendingFocusResult = result;
            _focusedAuditResultId = result.Id;
            _currentPage = Math.Clamp(result.Page, 1, _currentPages.Count);
            await LoadCurrentPageImageAsync();
        }
        catch (Exception ex)
        {
            ShowError("Jump To Result", ex);
        }
    }

    private void FocusPreviewOnResult(AuditResultDto result)
    {
        if (_currentBitmap is null)
        {
            return;
        }

        PageMetaDto? meta = _currentPages.FirstOrDefault(p => p.PageNumber == result.Page);
        if (meta is null || result.Bbox.Count != 4)
        {
            return;
        }

        double scaleX = meta.PageWidth > 0 ? _currentBitmap.PixelWidth / meta.PageWidth : 1.0;
        double scaleY = meta.PageHeight > 0 ? _currentBitmap.PixelHeight / meta.PageHeight : 1.0;
        double x = result.Bbox[0] * scaleX;
        double y = result.Bbox[1] * scaleY;
        double width = Math.Max(8, (result.Bbox[2] - result.Bbox[0]) * scaleX);
        double height = Math.Max(8, (result.Bbox[3] - result.Bbox[1]) * scaleY);

        void ScrollToTarget()
        {
            double scaledCenterX = (x + width / 2) * _zoomFactor;
            double scaledCenterY = (y + height / 2) * _zoomFactor;
            double targetX = Math.Max(0, scaledCenterX - PreviewScrollViewer.ViewportWidth / 2);
            double targetY = Math.Max(0, scaledCenterY - PreviewScrollViewer.ViewportHeight / 2);
            PreviewScrollViewer.ScrollToHorizontalOffset(targetX);
            PreviewScrollViewer.ScrollToVerticalOffset(targetY);
            _pendingFocusResult = null;
            DrawAnnotations();
        }

        PreviewScrollViewer.UpdateLayout();
        Dispatcher.BeginInvoke(ScrollToTarget, DispatcherPriority.Background);
    }

    private void StrategiesListBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (StrategiesListBox.SelectedItem is not StrategyDto strategy)
        {
            return;
        }
        LoadStrategyEditor(strategy);
    }

    private void NewStrategyButton_Click(object sender, RoutedEventArgs e)
    {
        StrategiesListBox.SelectedItem = null;
        ClearStrategyEditor();
    }

    private async void DeleteStrategyButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            if (StrategiesListBox.SelectedItem is not StrategyDto strategy)
            {
                MessageBox.Show("Select a strategy to delete.", "Delete Strategy", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            MessageBoxResult confirm = MessageBox.Show(
                $"Delete strategy '{strategy.Name}'?",
                "Delete Strategy",
                MessageBoxButton.YesNo,
                MessageBoxImage.Question);
            if (confirm != MessageBoxResult.Yes)
            {
                return;
            }

            await _apiClient.DeleteStrategyAsync(strategy.Id);
            ClearStrategyEditor();
            await LoadStrategiesAsync();
        }
        catch (Exception ex)
        {
            ShowError("Delete Strategy", ex);
        }
    }

    private void AddRuleButton_Click(object sender, RoutedEventArgs e)
    {
        string nextId = $"R{_strategyRules.Count + 1:000}";
        _strategyRules.Add(new RuleEditorModel
        {
            Id = nextId,
            Title = "New Rule",
            Description = "Describe the check condition",
            Severity = "medium",
            IsRequired = true,
        });
    }

    private void RemoveRuleButton_Click(object sender, RoutedEventArgs e)
    {
        if (RulesDataGrid.SelectedItem is RuleEditorModel selected)
        {
            _strategyRules.Remove(selected);
        }
    }

    private async void SaveStrategyButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            StrategyUpsertRequest request = BuildStrategyRequestFromEditor();
            if (string.IsNullOrWhiteSpace(request.Name))
            {
                MessageBox.Show("Strategy name is required.", "Save Strategy", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            if (request.Rules.Count == 0)
            {
                MessageBox.Show("Add at least one rule.", "Save Strategy", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            if (request.Rules.Any(rule => string.IsNullOrWhiteSpace(rule.Title) || string.IsNullOrWhiteSpace(rule.Description)))
            {
                MessageBox.Show("Each rule needs title and description.", "Save Strategy", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            StrategyDto saved;
            if (string.IsNullOrWhiteSpace(_editingStrategyId))
            {
                saved = await _apiClient.CreateStrategyAsync(request);
            }
            else
            {
                saved = await _apiClient.UpdateStrategyAsync(_editingStrategyId, request);
            }

            await LoadStrategiesAsync(saved.Id);
            StrategiesListBox.SelectedItem = _strategies.FirstOrDefault(x => x.Id == saved.Id);
            AuditStrategyComboBox.SelectedItem = _strategies.FirstOrDefault(x => x.Id == saved.Id);
        }
        catch (Exception ex)
        {
            ShowError("Save Strategy", ex);
        }
    }
}
