import { useCallback, useEffect, useRef, useState } from "react";
import { UploadCloud } from "lucide-react";

import StatusPill from "../components/StatusPill";
import ManualRequirementModal from "../components/ManualRequirementModal";
import {
  extractRequirements,
  extractSourceText,
  listSources,
  uploadSource,
} from "../../../api/requirementsApi";
import { useToast } from "../../../hooks/useToast";
import "../styles/requirements.css";

function SourcesPanel({ projectId }) {
  const { showToast } = useToast();
  const fileInputRef = useRef(null);

  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);

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

  async function handleFileChange(event) {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) return;

    setUploading(true);
    setLoadError("");

    try {
      // 1. Upload the document
      const uploadedSource = await uploadSource(projectId, file);

      const sourceId = uploadedSource?.source_id || uploadedSource?.id;

      if (!sourceId) {
        throw new Error(
          "Document uploaded, but the source ID was not returned."
        );
      }

      showToast("Document uploaded. Extracting text...", "success");

      await fetchSources();

      // 2. Automatically extract text from the document
      await extractSourceText(projectId, sourceId);

      showToast("Text extracted. Finding requirements...", "success");

      await fetchSources();

      // 3. Automatically extract requirements
      const result = await extractRequirements(projectId, sourceId);

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

  return (
    <div>
      <div className="workspace-header">
        <h2>Documents &amp; Sources</h2>

        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setManualOpen(true)}
            disabled={uploading}
          >
            Add Manually
          </button>

          <button
            type="button"
            className="btn btn-primary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            <UploadCloud size={16} />

            {uploading
              ? "Processing Document..."
              : "Upload Document"}
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt"
            hidden
            onChange={handleFileChange}
          />
        </div>
      </div>

      {loading && (
        <p className="muted-text">
          Loading sources...
        </p>
      )}

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

      {!loading && !loadError && sources.length === 0 && (
        <div className="table-state">
          <p>
            No sources yet. Upload a document or add a requirement
            manually.
          </p>
        </div>
      )}

      {!loading && !loadError && sources.length > 0 && (
        <div className="req-source-list">
          {sources.map((source) => (
            <div
              key={source.id}
              className="req-source-row"
            >
              <div>
                <strong>
                  {source.original_filename || "Manual entry"}
                </strong>

                <div className="muted-text">
                  {source.source_type?.toUpperCase() || "SOURCE"}
                </div>

                {source.extraction_error && (
                  <div className="form-error">
                    {source.extraction_error}
                  </div>
                )}
              </div>

              <StatusPill
                status={source.processing_status}
              />
            </div>
          ))}
        </div>
      )}

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