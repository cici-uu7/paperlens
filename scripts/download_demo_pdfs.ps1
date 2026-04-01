$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$outputDir = Join-Path $projectDir "data\raw_docs"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$papers = @(
    @{ file = "layoutlm_1912.13318.pdf"; title = "LayoutLM"; url = "https://arxiv.org/pdf/1912.13318.pdf" },
    @{ file = "layoutlmv2_2012.14740.pdf"; title = "LayoutLMv2"; url = "https://arxiv.org/pdf/2012.14740.pdf" },
    @{ file = "layoutlmv3_2204.08387.pdf"; title = "LayoutLMv3"; url = "https://arxiv.org/pdf/2204.08387.pdf" },
    @{ file = "docformer_2106.11539.pdf"; title = "DocFormer"; url = "https://arxiv.org/pdf/2106.11539.pdf" },
    @{ file = "donut_2111.15664.pdf"; title = "Donut"; url = "https://arxiv.org/pdf/2111.15664.pdf" },
    @{ file = "nougat_2308.13418.pdf"; title = "Nougat"; url = "https://arxiv.org/pdf/2308.13418.pdf" },
    @{ file = "docllm_2401.00908.pdf"; title = "DocLLM"; url = "https://arxiv.org/pdf/2401.00908.pdf" },
    @{ file = "colpali_2407.01449.pdf"; title = "ColPali"; url = "https://arxiv.org/pdf/2407.01449.pdf" },
    @{ file = "rag_2005.11401.pdf"; title = "RAG"; url = "https://arxiv.org/pdf/2005.11401.pdf" },
    @{ file = "self_rag_2310.11511.pdf"; title = "Self-RAG"; url = "https://arxiv.org/pdf/2310.11511.pdf" }
)

foreach ($paper in $papers) {
    $target = Join-Path $outputDir $paper.file
    Write-Host "Downloading $($paper.title) -> $target"
    & curl.exe -L $paper.url -o $target --fail --silent --show-error

    if (-not (Test-Path -LiteralPath $target)) {
        throw "Download failed: $($paper.file)"
    }

    $item = Get-Item -LiteralPath $target
    if ($item.Length -lt 10240) {
        throw "Downloaded file is unexpectedly small: $($paper.file)"
    }
}

Write-Host ""
Write-Host "Download finished. Files:"
Get-ChildItem -LiteralPath $outputDir -File |
    Sort-Object Name |
    Select-Object Name, Length, LastWriteTime
