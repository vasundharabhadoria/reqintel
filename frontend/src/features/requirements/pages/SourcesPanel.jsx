import { useCallback, useEffect, useRef, useState } from "react";
import {
  FileText,
  FileType2,
  File,
  UploadCloud,
  X,
  CloudUpload,
  CheckCircle2,
  Mail,
  MoreVertical,
  Eye,
  Download,
  Trash2,
} from "lucide-react";

import StatusPill from "../components/StatusPill";
import ManualRequirementModal from "../components/ManualRequirementModal";

import {
  deleteSource,
  extractRequirements,
  extractSourceText,
  getSourceFile,
  listSources,
  uploadSource,
} from "../../../api/requirementsApi";

import { useToast } from "../../../hooks/useToast";
import "../styles/requirements.css";

function formatDate(value) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
}

function getFileExtension(source) {
  const filename = source?.original_filename || "";

  const extension = filename
    .split(".")
    .pop()
    ?.toUpperCase();

  return extension || source?.source_type?.toUpperCase() || "SOURCE";
}

function getFileIcon(source) {
  const type = getFileExtension(source);

  if (type === "PDF") {
    return <FileText size={22} />;
  }

  if (type === "DOCX" || type === "DOC") {
    return <FileType2 size={22} />;
  }

  if (type === "TXT") {
    return <File size={22} />;
  }

  return <FileText size={22} />;
}

function SourcesPanel({ projectId }) {
  const { showToast } = useToast();
  const fileInputRef = useRef(null);

  const [sources, setSources] = useState([]);
  const [openActionMenu, setOpenActionMenu] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [uploading, setUploading] = useState(false);

  const [manualOpen, setManualOpen] = useState(false);
  const [uploadMenuOpen, setUploadMenuOpen] = useState(false);

  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadFileType, setUploadFileType] = useState("pdf");
  const [selectedFile, setSelectedFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);

  const fetchSources = useCallback(async () => {
    setLoading(true);
    setLoadError("");

    try {
      const data = await listSources(projectId);
      setSources(data.items || []);
    } catch (err) {
      setLoadError(err.message || "Failed to load sources.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  function closeUploadModal() {
    setUploadModalOpen(false);
    setSelectedFile(null);
    setDragActive(false);
  }

  function openPdfModal() {
    setUploadMenuOpen(false);
    setSelectedFile(null);
    setDragActive(false);
    setUploadFileType("pdf");
    setUploadModalOpen(true);
  }

  function openFilePicker(type) {
    setUploadMenuOpen(false);
    setSelectedFile(null);
    setDragActive(false);

    if (type === ".pdf") {
      setUploadFileType("pdf");
    } else if (type.includes("docx")) {
      setUploadFileType("docx");
    } else if (type === ".txt") {
      setUploadFileType("txt");
    }

    setUploadModalOpen(true);
  }

  function selectPdfFile(file) {
    if (!file) return;

    const isPdf =
      uploadFileType === "pdf" &&
      file.type === "application/pdf";

    const isDocx =
      uploadFileType === "docx" &&
      (
        file.type ===
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
        file.name.toLowerCase().endsWith(".docx") ||
        file.name.toLowerCase().endsWith(".doc")
      );

    const isTxt =
      uploadFileType === "txt" &&
      (
        file.type === "text/plain" ||
        file.name.toLowerCase().endsWith(".txt")
      );

    if (!isPdf && !isDocx && !isTxt) {
      showToast(
        "Please select a " + uploadFileType.toUpperCase() + " file.",
        "error"
      );
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      showToast(
        "File size must be less than 50 MB.",
        "error"
      );
      return;
    }

    setSelectedFile(file);
  }

  async function processFile(file) {
    if (!file) return;

    setUploading(true);
    setLoadError("");

    try {
      const uploadedSource = await uploadSource(projectId, file);

      const sourceId =
        uploadedSource?.source_id ||
        uploadedSource?.id;

      if (!sourceId) {
        throw new Error(
          "Document uploaded, but the source ID was not returned."
        );
      }

      showToast(
        "Document uploaded. Extracting text...",
        "success"
      );

      await fetchSources();

      await extractSourceText(
        projectId,
        sourceId
      );

      showToast(
        "Text extracted. Finding requirements...",
        "success"
      );

      await fetchSources();

      const result = await extractRequirements(
        projectId,
        sourceId
      );

      showToast(
        `${result?.requirements_created || 0} requirement(s) extracted successfully.`,
        "success"
      );

      await fetchSources();
    } catch (err) {
      showToast(
        err.message || "Document processing failed.",
        "error"
      );

      await fetchSources();
    } finally {
      setUploading(false);
    }
  }

  async function confirmPdfUpload() {
    if (!selectedFile || uploading) return;

    const file = selectedFile;

    closeUploadModal();

    await processFile(file);
  }

  function handleNormalFileChange(event) {
    const file = event.target.files?.[0];

    event.target.value = "";

    if (!file) return;

    processFile(file);
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragActive(false);

    const file = event.dataTransfer.files?.[0];

    selectPdfFile(file);
  }

  async function handleViewSource(source) {
    setOpenActionMenu(null);

    try {
      const result = await getSourceFile(projectId, source.id);

      if (result instanceof Blob) {
        const url = URL.createObjectURL(result);
        window.open(url, "_blank", "noopener,noreferrer");
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        return;
      }

      const url =
        result?.url ||
        result?.file_url ||
        result?.download_url ||
        result?.data?.url;

      if (url) {
        window.open(url, "_blank", "noopener,noreferrer");
        return;
      }

      throw new Error("The document file could not be opened.");
    } catch (err) {
      showToast(err.message || "Unable to view document.", "error");
    }
  }

  async function handleDownloadSource(source) {
    setOpenActionMenu(null);

    try {
      const result = await getSourceFile(projectId, source.id);

      if (result instanceof Blob) {
        const url = URL.createObjectURL(result);
        const link = document.createElement("a");

        link.href = url;
        link.download = source.original_filename || "document";

        document.body.appendChild(link);
        link.click();
        link.remove();

        setTimeout(() => URL.revokeObjectURL(url), 1000);
        return;
      }

      const url =
        result?.url ||
        result?.file_url ||
        result?.download_url ||
        result?.data?.url;

      if (url) {
        const link = document.createElement("a");

        link.href = url;
        link.download = source.original_filename || "document";
        link.target = "_blank";

        document.body.appendChild(link);
        link.click();
        link.remove();

        return;
      }

      throw new Error("The document file could not be downloaded.");
    } catch (err) {
      showToast(err.message || "Unable to download document.", "error");
    }
  }

  function requestDeleteSource(source) {
    setOpenActionMenu(null);
    setDeleteTarget(source);
  }

  async function confirmDeleteSource() {
    if (!deleteTarget || deleting) return;

    setDeleting(true);

    try {
      await deleteSource(projectId, deleteTarget.id);

      setSources((current) =>
        current.filter((source) => source.id !== deleteTarget.id)
      );

      setDeleteTarget(null);

      showToast(
        "Document and all extracted requirements were permanently deleted.",
        "success"
      );
    } catch (err) {
      showToast(
        err.message || "Failed to delete document.",
        "error"
      );
    } finally {
      setDeleting(false);
    }
  }
  return (
    <div className="sources-panel">

      {/* =====================================================
          DOCUMENT HEADER
          ===================================================== */}

      <div className="sources-panel-header">
        <div>
          <h2>Uploaded Documents</h2>

          <p>
            Upload or add documents from different sources.
            Requirements will be extracted automatically.
          </p>
        </div>

        <div className="sources-actions">

          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setManualOpen(true)}
            disabled={uploading}
          >
            Add Manually
          </button>

          <div className="upload-menu-wrapper">

            <button
              type="button"
              className="btn btn-primary upload-menu-button"
              onClick={() =>
                setUploadMenuOpen((open) => !open)
              }
              disabled={uploading}
            >
              <UploadCloud size={18} />

              {uploading
                ? "Processing..."
                : "Upload Documents"}

              <span className="upload-menu-chevron">
                ▾
              </span>
            </button>

            {uploadMenuOpen && !uploading && (
              <div className="upload-menu">

                <button
                  type="button"
                  onClick={() => openFilePicker(".pdf")}
                >
                  <FileText size={17} />
                  <span>Upload PDF</span>
                </button>

                <button
                  type="button"
                  onClick={() =>
                    openFilePicker(".docx,.doc")
                  }
                >
                  <FileType2 size={17} />
                  <span>Upload DOCX</span>
                </button>

                <button
                  type="button"
                  onClick={() => openFilePicker(".txt")}
                >
                  <File size={17} />
                  <span>Upload TXT</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setUploadMenuOpen(false);
                    setManualOpen(true);
                  }}
                >
                  <Mail size={17} />
                  <span>Paste Client Email</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setUploadMenuOpen(false);
                    setManualOpen(true);
                  }}
                >
                  <FileText size={17} />
                  <span>Paste Manual Text</span>
                </button>

              </div>
            )}

          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt"
            hidden
            onChange={handleNormalFileChange}
          />

        </div>
      </div>

      {/* =====================================================
          LOADING
          ===================================================== */}

      {loading && (
        <div className="sources-loading">
          <div className="sources-loading-spinner" />
          <span>Loading documents...</span>
        </div>
      )}

      {/* =====================================================
          ERROR
          ===================================================== */}

      {!loading && loadError && (
        <div className="table-state table-state-error">
          <p>{loadError}</p>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={fetchSources}
          >
            Try Again
          </button>
        </div>
      )}

      {/* =====================================================
          EMPTY STATE
          ===================================================== */}

      {!loading &&
        !loadError &&
        sources.length === 0 && (
          <div className="sources-empty">
            <FileText size={34} />

            <h3>No documents uploaded</h3>

            <p>
              Upload a document to start extracting
              requirements.
            </p>
          </div>
        )}

      {/* =====================================================
          DOCUMENT TABLE
          ===================================================== */}

      {!loading &&
        !loadError &&
        sources.length > 0 && (
          <div className="sources-table-wrapper">

            <div className="sources-table">

              <div className="sources-table-header">

                <div className="sources-col-number">
                  #
                </div>

                <div className="sources-col-name">
                  Document Name
                </div>

                <div className="sources-col-type">
                  Type
                </div>

                <div className="sources-col-date">
                  Uploaded On
                </div>

                <div className="sources-col-status">
                  Status
                </div>

                <div className="sources-col-actions">
                  Actions
                </div>

              </div>

              {sources.map((source, index) => {

                const filename =
                  source.original_filename ||
                  "Manual entry";

                const type =
                  getFileExtension(source);

                const uploadedDate =
                  source.created_at ||
                  source.uploaded_at ||
                  source.created_on;

                return (
                  <div
                    key={source.id}
                    className="sources-table-row"
                  >

                    <div className="sources-col-number">
                      {index + 1}
                    </div>

                    <div className="sources-col-name">

                      <div className="source-file-info">

                        <div
                          className={`source-file-icon source-file-icon-${type.toLowerCase()}`}
                        >
                          {getFileIcon(source)}
                        </div>

                        <div>
                          <strong>
                            {filename}
                          </strong>

                          {source.extraction_error && (
                            <div className="source-error">
                              {source.extraction_error}
                            </div>
                          )}
                        </div>

                      </div>

                    </div>

                    <div className="sources-col-type">
                      <span
                        className={`source-type source-type-${type.toLowerCase()}`}
                      >
                        {type}
                      </span>
                    </div>

                    <div className="sources-col-date">
                      {formatDate(uploadedDate)}
                    </div>

                    <div className="sources-col-status">
                      <StatusPill
                        status={
                          source.processing_status
                        }
                      />
                    </div>

                    <div className="sources-col-actions">
                      <div className="source-actions-menu">
                        <button
                          type="button"
                          className="source-actions-trigger"
                          aria-label={`Actions for ${filename}`}
                          aria-expanded={openActionMenu === source.id}
                          onClick={() =>
                            setOpenActionMenu(
                              openActionMenu === source.id ? null : source.id
                            )
                          }
                        >
                          <MoreVertical size={20} />
                        </button>

                        {openActionMenu === source.id && (
                          <div className="source-actions-dropdown">
                            <button
                              type="button"
                              onClick={() => handleViewSource(source)}
                            >
                              <Eye size={16} />
                              <span>View</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => handleDownloadSource(source)}
                            >
                              <Download size={16} />
                              <span>Download</span>
                            </button>

                            <button
                              type="button"
                              className="source-action-delete"
                              onClick={() => requestDeleteSource(source)}
                            >
                              <Trash2 size={16} />
                              <span>Delete</span>
                            </button>
                          </div>
                        )}

      {deleteTarget && (
        <div
          className="delete-confirm-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !deleting) {
              setDeleteTarget(null);
            }
          }}
        >
          <div
            className="delete-confirm-modal"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="delete-confirm-close"
              onClick={() => !deleting && setDeleteTarget(null)}
              aria-label="Close"
            >
              <X size={20} />
            </button>

            <div className="delete-confirm-icon">
              <Trash2 size={22} />
            </div>

            <h2>Delete document?</h2>

            <p>
              Are you sure you want to permanently delete
              <strong> {deleteTarget.original_filename || "Manual entry"}</strong>?
            </p>

            <div className="delete-confirm-warning">
              <strong>This action cannot be undone.</strong>
              <span>
                Deleting this document will also permanently delete
                all extracted requirements and their versions.
              </span>
            </div>

            <div className="delete-confirm-actions">
              <button
                type="button"
                className="btn"
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
              >
                Cancel
              </button>

              <button
                type="button"
                className="btn delete-confirm-delete-button"
                onClick={confirmDeleteSource}
                disabled={deleting}
              >
                <Trash2 size={16} />
                {deleting ? "Deleting..." : "Delete Permanently"}
              </button>
            </div>
          </div>
        </div>
      )}

                      </div>
                    </div>

                  </div>
                );
              })}

            </div>

          </div>
        )}

      {/* =====================================================
          INFORMATION
          ===================================================== */}

      <div className="sources-info-box">
        <FileText size={20} />

        <div>
          <strong>
            Automatic requirement extraction
          </strong>

          <p>
            Once a document is uploaded, ReqIntel
            automatically extracts its text and identifies
            project requirements.
          </p>
        </div>
      </div>

      {/* =====================================================
          PDF UPLOAD MODAL
          ===================================================== */}

      {uploadModalOpen && (
        <div
          className="upload-modal-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeUploadModal();
            }
          }}
        >
          <div
            className="upload-modal"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >

            {/* HEADER */}

            <div className="upload-modal-header">

              <div className="upload-modal-title-wrap">

                <div className="upload-modal-pdf-icon">
                  <FileText size={20} />
                </div>

                <div>
                  <h2>Upload {uploadFileType === "pdf" ? "PDF" : uploadFileType === "docx" ? "DOCX" : "TXT"} Document</h2>

                  <p>
  {selectedFile
    ? "Review the selected file before uploading."
    : `Select a ${
        uploadFileType === "pdf"
          ? "PDF"
          : uploadFileType === "docx"
            ? "DOCX"
            : "TXT"
      } file from your computer to upload.`}
</p>
                </div>

              </div>

              <button
                type="button"
                className="upload-modal-close"
                onClick={closeUploadModal}
                aria-label="Close"
              >
                <X size={21} />
              </button>

            </div>

            {/* EMPTY / DROP STATE */}

            {!selectedFile && (
              <>

                <div
                  className={`pdf-drop-zone ${
                    dragActive
                      ? "drag-active"
                      : ""
                  }`}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setDragActive(true);
                  }}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    setDragActive(true);
                  }}
                  onDragLeave={(event) => {
                    if (
                      event.currentTarget ===
                      event.target
                    ) {
                      setDragActive(false);
                    }
                  }}
                  onDrop={handleDrop}
                >

                  <div className="pdf-upload-icon">
                    <CloudUpload size={42} />
                  </div>

                  <strong>
                    Drag and drop your {uploadFileType.toUpperCase()} file here
                  </strong>

                  <span className="pdf-or">
                    or
                  </span>

                  <button
                    type="button"
                    className="choose-file-button"
                    onClick={() => {
                      if (fileInputRef.current) {
                        fileInputRef.current.accept = uploadFileType === "pdf" ? ".pdf" : uploadFileType === "docx" ? ".docx,.doc" : ".txt";

                        fileInputRef.current.click();
                      }
                    }}
                  >
                    Choose File
                  </button>

                  <small>
                    Maximum file size: 50 MB
                  </small>

                </div>

                <div className="upload-modal-footer">

                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={closeUploadModal}
                  >
                    Cancel
                  </button>

                </div>

              </>
            )}

            {/* SELECTED FILE STATE */}

            {selectedFile && (
              <>

                <div className="selected-success-message">
                  <CheckCircle2 size={19} />
                  <span>
                    File selected successfully!
                  </span>
                </div>

                <div className="selected-file-card">

                  <div className="selected-file-icon">
                    <FileText size={27} />
                  </div>

                  <div className="selected-file-details">

                    <strong>
                      {selectedFile.name}
                    </strong>

                    <span>
                      {(
                        selectedFile.size /
                        (1024 * 1024)
                      ).toFixed(2)}{" "}
                      MB
                    </span>

                  </div>

                  <button
                    type="button"
                    className="change-file-button"
                    onClick={() => {
                      setSelectedFile(null);
                      setDragActive(false);
                    }}
                  >
                    Change File
                  </button>

                </div>

                <p className="upload-processing-note">
                  File will be uploaded and processed automatically.
                </p>

                <div className="upload-supported-info">

                  <div>
                    <strong>
                      Supported format
                    </strong>

                    <span>{uploadFileType.toUpperCase()}</span>
                  </div>

                  <div>
                    <strong>
                      Maximum file size
                    </strong>

                    <span>
                      50 MB
                    </span>
                  </div>

                </div>

                <div className="upload-modal-footer">

                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={closeUploadModal}
                  >
                    Cancel
                  </button>

                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={uploading}
                    onClick={confirmPdfUpload}
                  >
                    {uploading
                      ? "Uploading..."
                      : "Upload"}
                  </button>

                </div>

              </>
            )}

          </div>
        </div>
      )}

      {/* =====================================================
          MANUAL REQUIREMENT MODAL
          ===================================================== */}

      <ManualRequirementModal
        open={manualOpen}
        onClose={() => setManualOpen(false)}
        projectId={projectId}
        onCreated={() =>
          showToast(
            "You can find it in the Requirements tab.",
            "success"
          )
        }
      />

    </div>
  );
}

export default SourcesPanel;





