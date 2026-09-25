import { useEffect, useMemo, useState } from "react";
import {
  Database,
  LogOut,
  Search,
  Plus,
  Pencil,
  Trash2,
  X,
  Settings,
  ChevronDown,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getCurrentUser, logoutUser } from "../../../api/authApi";
import { clearTokens } from "../../../api/tokenStorage";
import {
  getCategories,
  createCategory,
  updateCategory,
  deleteCategory as deleteCategoryApi,
  getRules,
  createRule,
  updateRule,
  deleteRule as deleteRuleApi,
} from "../../../api/masterModuleApi";
import "../master-module.css";

function MasterModulePage() {
  const navigate = useNavigate();

  const [categories, setCategories] = useState([]);
  const [rules, setRules] = useState([]);

  const [selectedCategoryId, setSelectedCategoryId] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");

  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [showRuleModal, setShowRuleModal] = useState(false);

  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [editingRuleId, setEditingRuleId] = useState(null);

  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [adminEmail, setAdminEmail] = useState("");

  const [notification, setNotification] = useState({
    open: false,
    type: "success",
    title: "",
    message: "",
  });

  const [deleteConfirmation, setDeleteConfirmation] = useState({
    open: false,
    type: null,
    id: null,
    title: "",
    message: "",
  });

  const [categoryForm, setCategoryForm] = useState({
    name: "",
    description: "",
    evaluationMode: "Issue",
  });

  const [ruleForm, setRuleForm] = useState({
    rule: "",
    description: "",
    ruleType: "Keyword",
    severity: "Medium",
    whyItMatters: "",
    recommendation: "",
    active: true,
  });

  function showNotification(type, title, message) {
    setNotification({
      open: true,
      type,
      title,
      message,
    });
  }

  function closeNotification() {
    setNotification((current) => ({
      ...current,
      open: false,
    }));
  }

  function normalizeValue(value) {
    return (value || "").trim().toLowerCase();
  }

  function isDuplicateCategoryName(name, currentId = null) {
    const normalizedName = normalizeValue(name);

    return categories.some(
      (category) =>
        category.id !== currentId &&
        normalizeValue(category.name) === normalizedName
    );
  }

  function isDuplicateRule(rule, categoryId, currentId = null) {
    const normalizedRule = normalizeValue(rule);

    return rules.some(
      (item) =>
        item.id !== currentId &&
        item.categoryId === categoryId &&
        normalizeValue(item.rule) === normalizedRule
    );
  }

  function openDeleteConfirmation(type, id, title, message) {
    setDeleteConfirmation({
      open: true,
      type,
      id,
      title,
      message,
    });
  }

  function closeDeleteConfirmation() {
    setDeleteConfirmation((current) => ({
      ...current,
      open: false,
    }));
  }

  async function confirmDelete() {
    const { type, id } = deleteConfirmation;

    closeDeleteConfirmation();

    if (type === "category") {
      await performDeleteCategory(id);
      return;
    }

    if (type === "rule") {
      await performDeleteRule(id);
    }
  }

  useEffect(() => {
    async function loadMasterModuleData() {
      try {
        const [currentUser, categoryData, ruleData] =
          await Promise.all([
            getCurrentUser(),
            getCategories(),
            getRules(),
          ]);

        const mappedCategories = (categoryData || []).map(
          (category) => ({
            id: category.id,
            name: category.name,
            description: category.description || "",
            evaluationMode:
              category.evaluation_mode || "Issue",
            isActive: category.is_active,
          })
        );

        const mappedRules = (ruleData || []).map((rule) => ({
          id: rule.id,
          categoryId: rule.category_id,
          rule: rule.rule,
          description: rule.description || "",
          ruleType: rule.rule_type,
          severity: rule.severity,
          whyItMatters: rule.why_it_matters || "",
          recommendation: rule.recommendation || "",
          active: rule.is_active,
        }));

        setAdminEmail(currentUser?.email || "");
        setCategories(mappedCategories);
        setRules(mappedRules);

        if (mappedCategories.length > 0) {
          setSelectedCategoryId(mappedCategories[0].id);
        }
      } catch (error) {
        console.error("MASTER MODULE LOAD ERROR:", error);
        showNotification(
          "error",
          "Unable to Load Master Module",
          error.message ||
            "Unable to load Master Module data."
        );
      }
    }

    loadMasterModuleData();
  }, []);

  const selectedCategory = categories.find(
    (category) => category.id === selectedCategoryId
  );

  const categoryRules = useMemo(() => {
    return rules.filter((rule) => {
      const belongsToCategory =
        rule.categoryId === selectedCategoryId;

      const matchesSearch = rule.rule
        .toLowerCase()
        .includes(searchTerm.toLowerCase());

      return belongsToCategory && matchesSearch;
    });
  }, [rules, selectedCategoryId, searchTerm]);

  function openCategoryModal(category = null) {
    if (category) {
      setEditingCategoryId(category.id);

      setCategoryForm({
        name: category.name || "",
        description: category.description || "",
        evaluationMode:
          category.evaluationMode || "Issue",
      });
    } else {
      setEditingCategoryId(null);

      setCategoryForm({
        name: "",
        description: "",
        evaluationMode: "Issue",
      });
    }

    setShowCategoryModal(true);
  }

  function closeCategoryModal() {
    setEditingCategoryId(null);

    setCategoryForm({
      name: "",
      description: "",
      evaluationMode: "Issue",
    });

    setShowCategoryModal(false);
  }

  function openRuleModal() {
    setEditingRuleId(null);

    setRuleForm({
      rule: "",
      description: "",
      ruleType: "Keyword",
      severity: "Medium",
      whyItMatters: "",
      recommendation: "",
      active: true,
    });

    setShowRuleModal(true);
  }

  function handleEditRule(rule) {
    setEditingRuleId(rule.id);

    setRuleForm({
      rule: rule.rule || "",
      description: rule.description || "",
      ruleType: rule.ruleType || "Keyword",
      severity: rule.severity || "Medium",
      whyItMatters: rule.whyItMatters || "",
      recommendation: rule.recommendation || "",
      active: Boolean(rule.active),
    });

    setShowRuleModal(true);
  }

  async function handleCategorySubmit(event) {
    event.preventDefault();

    if (!categoryForm.name.trim()) {
      return;
    }

    if (isDuplicateCategoryName(
      categoryForm.name,
      editingCategoryId
    )) {
      showNotification(
        "error",
        "Duplicate Category",
        "This category already exists."
      );
      return;
    }

    try {
      const payload = {
        name: categoryForm.name.trim(),
        description:
          categoryForm.description.trim(),
        evaluation_mode:
          categoryForm.evaluationMode,
      };

      if (editingCategoryId) {
        const updatedCategory =
          await updateCategory(
            editingCategoryId,
            payload
          );

        const updatedCategoryData = {
          id: updatedCategory.id,
          name: updatedCategory.name,
          description:
            updatedCategory.description || "",
          evaluationMode:
            updatedCategory.evaluation_mode ||
            "Issue",
          isActive:
            updatedCategory.is_active,
        };

        setCategories((current) =>
          current.map((category) =>
            category.id === editingCategoryId
              ? updatedCategoryData
              : category
          )
        );
      } else {
        const createdCategory =
          await createCategory(
            categoryForm.name.trim(),
            categoryForm.description.trim(),
            categoryForm.evaluationMode
          );

        const newCategory = {
          id: createdCategory.id,
          name: createdCategory.name,
          description:
            createdCategory.description || "",
          evaluationMode:
            createdCategory.evaluation_mode ||
            "Issue",
          isActive:
            createdCategory.is_active,
        };

        setCategories((current) => [
          ...current,
          newCategory,
        ]);

        setSelectedCategoryId(
          newCategory.id
        );
      }

      const wasEditing = Boolean(editingCategoryId);
      closeCategoryModal();

      showNotification(
        "success",
        wasEditing ? "Category Updated" : "Category Created",
        wasEditing
          ? "The category was updated successfully."
          : "The category was created successfully."
      );
    } catch (error) {
      console.error(
        editingCategoryId
          ? "UPDATE CATEGORY ERROR:"
          : "CREATE CATEGORY ERROR:",
        error
      );

      const errorMessage = error.message || "";

      showNotification(
        "error",
        errorMessage.toLowerCase().includes("duplicate") ||
          errorMessage.toLowerCase().includes("unique")
          ? "Duplicate Category"
          : editingCategoryId
            ? "Unable to Update Category"
            : "Unable to Create Category",
        errorMessage.toLowerCase().includes("duplicate") ||
          errorMessage.toLowerCase().includes("unique")
          ? "This category already exists."
          : errorMessage ||
              (editingCategoryId
                ? "Unable to update category."
                : "Unable to create category.")
      );
    }
  }

  async function handleRuleSubmit(event) {
    event.preventDefault();

    if (
      !ruleForm.rule.trim() ||
      !selectedCategoryId
    ) {
      return;
    }

    if (
      isDuplicateRule(
        ruleForm.rule,
        selectedCategoryId,
        editingRuleId
      )
    ) {
      showNotification(
        "error",
        "Duplicate Rule",
        "This rule already exists in the selected category."
      );
      return;
    }

    const payload = {
      category_id: selectedCategoryId,
      rule: ruleForm.rule.trim(),
      description:
        ruleForm.description.trim(),
      why_it_matters:
        ruleForm.whyItMatters.trim(),
      recommendation:
        ruleForm.recommendation.trim(),
      rule_type: ruleForm.ruleType,
      severity: ruleForm.severity,
      is_active: ruleForm.active,
    };

    try {
      if (editingRuleId) {
        const updatedRule = await updateRule(
          editingRuleId,
          payload
        );

        setRules((current) =>
          current.map((item) =>
            item.id === editingRuleId
              ? {
                  ...item,
                  categoryId:
                    updatedRule.category_id,
                  rule: updatedRule.rule,
                  description:
                    updatedRule.description ||
                    "",
                  ruleType:
                    updatedRule.rule_type,
                  severity:
                    updatedRule.severity,
                  whyItMatters:
                    updatedRule.why_it_matters ||
                    "",
                  recommendation:
                    updatedRule.recommendation ||
                    "",
                  active:
                    updatedRule.is_active,
                }
              : item
          )
        );
      } else {
        const createdRule =
          await createRule(payload);

        const newRule = {
          id: createdRule.id,
          categoryId:
            createdRule.category_id,
          rule: createdRule.rule,
          description:
            createdRule.description || "",
          ruleType:
            createdRule.rule_type,
          severity:
            createdRule.severity,
          whyItMatters:
            createdRule.why_it_matters || "",
          recommendation:
            createdRule.recommendation || "",
          active:
            createdRule.is_active,
        };

        setRules((current) => [
          ...current,
          newRule,
        ]);
      }

      const wasEditing = Boolean(editingRuleId);
      setEditingRuleId(null);
      setShowRuleModal(false);

      showNotification(
        "success",
        wasEditing ? "Rule Updated" : "Rule Created",
        wasEditing
          ? "The rule was updated successfully."
          : "The rule was created successfully."
      );
    } catch (error) {
      console.error(
        editingRuleId
          ? "UPDATE RULE ERROR:"
          : "CREATE RULE ERROR:",
        error
      );

      const errorMessage = error.message || "";
      const isDuplicate =
        errorMessage.toLowerCase().includes("duplicate") ||
        errorMessage.toLowerCase().includes("unique");

      showNotification(
        "error",
        isDuplicate
          ? "Duplicate Rule"
          : editingRuleId
            ? "Unable to Update Rule"
            : "Unable to Create Rule",
        isDuplicate
          ? "This rule already exists in the selected category."
          : errorMessage ||
              (editingRuleId
                ? "Unable to update rule."
                : "Unable to create rule.")
      );
    }
  }

  function deleteCategory(categoryId) {
    const category = categories.find(
      (item) => item.id === categoryId
    );

    if (!category) {
      return;
    }

    const categoryRuleCount = rules.filter(
      (rule) =>
        rule.categoryId === categoryId
    ).length;

    openDeleteConfirmation(
      "category",
      categoryId,
      "Delete Category?",
      `Delete category "${category.name}" and all ${categoryRuleCount} rule${
        categoryRuleCount === 1 ? "" : "s"
      } inside it?`
    );
  }

  async function performDeleteCategory(categoryId) {
    const category = categories.find(
      (item) => item.id === categoryId
    );

    if (!category) {
      return;
    }

    try {
      await deleteCategoryApi(categoryId);

      const remainingCategories =
        categories.filter(
          (item) => item.id !== categoryId
        );

      setCategories(
        remainingCategories
      );

      setRules((current) =>
        current.filter(
          (rule) =>
            rule.categoryId !== categoryId
        )
      );

      if (
        selectedCategoryId === categoryId
      ) {
        if (remainingCategories.length > 0) {
          setSelectedCategoryId(
            remainingCategories[0].id
          );
        } else {
          setSelectedCategoryId(null);
        }

        setSearchTerm("");
      }

      showNotification(
        "success",
        "Category Deleted",
        `"${category.name}" was deleted successfully.`
      );
    } catch (error) {
      console.error(
        "DELETE CATEGORY ERROR:",
        error
      );

      showNotification(
        "error",
        "Unable to Delete Category",
        error.message ||
          "Unable to delete category."
      );
    }
  }

  function deleteRule(ruleId) {
    const rule = rules.find(
      (item) => item.id === ruleId
    );

    if (!rule) {
      return;
    }

    openDeleteConfirmation(
      "rule",
      ruleId,
      "Delete Rule?",
      `Delete the rule "${rule.rule}"?`
    );
  }

  async function performDeleteRule(ruleId) {
    const rule = rules.find(
      (item) => item.id === ruleId
    );

    if (!rule) {
      return;
    }

    try {
      await deleteRuleApi(ruleId);

      setRules((current) =>
        current.filter(
          (rule) => rule.id !== ruleId
        )
      );

      showNotification(
        "success",
        "Rule Deleted",
        `"${rule.rule}" was deleted successfully.`
      );
    } catch (error) {
      console.error(
        "DELETE RULE ERROR:",
        error
      );

      showNotification(
        "error",
        "Unable to Delete Rule",
        error.message ||
          "Unable to delete rule."
      );
    }
  }

  async function handleLogout() {
    try {
      await logoutUser();
    } catch {
      // Clear local authentication state even if
      // the server-side logout request fails.
    } finally {
      clearTokens();
      window.location.href = "/login";
    }
  }

  return (
    <div className="master-module-page">

      {/* =========================
          TOP BAR
      ========================= */}

      <header className="master-topbar">

        <div className="master-brand">

          <div className="master-logo-wrapper">
            <span className="master-logo-mark">
              R
            </span>

            <span className="master-logo">
              ReqIntel
            </span>
          </div>

          <span className="master-ai-badge">
            <span className="master-ai-icon">
              ✣
            </span>
            AI-POWERED
          </span>

        </div>

        <div className="master-profile-wrapper">

          <button
            type="button"
            className="master-user"
            onClick={() =>
              setShowProfileMenu(
                (current) => !current
              )
            }
            aria-expanded={showProfileMenu}
          >
            <span className="master-user-avatar">
              A
            </span>

            <span>Admin</span>

            <ChevronDown size={17} />
          </button>

          {showProfileMenu && (
            <div className="master-profile-menu">

              <div className="master-profile-email">
                {adminEmail ||
                  "Admin account"}
              </div>

              <button
                type="button"
                className="master-profile-logout"
                onClick={handleLogout}
              >
                <LogOut size={17} />
                <span>Logout</span>
              </button>

            </div>
          )}

        </div>

      </header>

      {/* =========================
          SIDEBAR
      ========================= */}

      <aside className="master-sidebar">

        <div className="master-sidebar-menu">

          <div className="master-sidebar-item active">

            <Database size={23} />

            <span>
              Master Module
            </span>

          </div>

        </div>

        <div className="master-sidebar-bottom">

          <button
            type="button"
            className="master-sidebar-item logout"
            onClick={handleLogout}
          >
            <LogOut size={23} />

            <span>
              Logout
            </span>

          </button>

        </div>

      </aside>

      {/* =========================
          MAIN CONTENT
      ========================= */}

      <main className="master-content">

        <section className="master-heading-row">

          <div>

            <h1>
              Master Module
            </h1>

            <h2>
              Manage Rule Engine Configuration
            </h2>

            <p>
              Add, edit, or delete categories and
              rules used by the Rule Engine for
              requirement analysis.
            </p>

          </div>

          <div className="master-info-card">

            <Settings size={27} />

            <span>
              Changes made here will be used by
              the Rule Engine for requirement
              analysis.
            </span>

          </div>

        </section>

        <section className="master-workspace">

          {/* =========================
              CATEGORIES
          ========================= */}

          <div className="categories-panel">

            <div className="panel-heading">

              <h3>
                Categories
              </h3>

              <button
                className="primary-button"
                onClick={() =>
                  openCategoryModal()
                }
              >
                <Plus size={18} />
                Add Category
              </button>

            </div>

            <div className="category-list">

              {categories.map((category) => {

                const ruleCount =
                  rules.filter(
                    (rule) =>
                      rule.categoryId ===
                      category.id
                  ).length;

                return (
                  <div
                    key={category.id}
                    className={`category-item ${
                      selectedCategoryId ===
                      category.id
                        ? "selected"
                        : ""
                    }`}
                  >

                    <button
                      type="button"
                      className="category-select-button"
                      onClick={() => {
                        setSelectedCategoryId(
                          category.id
                        );

                        setSearchTerm("");
                      }}
                    >

                      <span>
                        {category.name}
                      </span>

                      <span className="category-count">
                        {ruleCount}
                      </span>

                    </button>

                    <div className="category-actions">

                      <button
                        type="button"
                        className="category-action-button edit"
                        title="Edit category"
                        onClick={() =>
                          openCategoryModal(
                            category
                          )
                        }
                      >
                        <Pencil size={16} />
                      </button>

                      <button
                        type="button"
                        className="category-action-button delete"
                        title="Delete category"
                        onClick={() =>
                          deleteCategory(
                            category.id
                          )
                        }
                      >
                        <Trash2 size={16} />
                      </button>

                    </div>

                  </div>
                );
              })}

            </div>

          </div>

          {/* =========================
              RULES
          ========================= */}

          <div className="rules-panel">

            <div className="rules-heading">

              <div>

                <h3>
                  Rules for :{" "}
                  {selectedCategory?.name}
                </h3>

                <p>
                  {selectedCategory?.description}
                </p>

              </div>

              <div className="rules-actions">

                <div className="search-box">

                  <Search size={19} />

                  <input
                    type="text"
                    placeholder="Search rules..."
                    value={searchTerm}
                    onChange={(event) =>
                      setSearchTerm(
                        event.target.value
                      )
                    }
                  />

                </div>

                <button
                  className="primary-button"
                  onClick={openRuleModal}
                >
                  <Plus size={18} />
                  Add Rule
                </button>

              </div>

            </div>

            <div className="rules-table-wrapper">

              <table className="rules-table">

                <thead>

                  <tr>

                    <th>
                      #
                    </th>

                    <th>
                      Rule
                    </th>

                    <th>
                      Description
                    </th>

                    <th>
                      Rule Type
                    </th>

                    <th>
                      Severity
                    </th>

                    <th>
                      Status
                    </th>

                    <th>
                      Actions
                    </th>

                  </tr>

                </thead>

                <tbody>

                  {categoryRules.length === 0 ? (

                    <tr>

                      <td
                        colSpan="7"
                        className="empty-state"
                      >
                        No rules found.
                      </td>

                    </tr>

                  ) : (

                    categoryRules.map(
                      (rule, index) => (

                        <tr key={rule.id}>

                          <td>
                            {index + 1}
                          </td>

                          <td className="rule-name">
                            {rule.rule}
                          </td>

                          <td>
                            {rule.description}
                          </td>

                          <td>
                            {rule.ruleType}
                          </td>

                          <td>

                            <span
                              className={`severity-badge ${rule.severity.toLowerCase()}`}
                            >
                              {rule.severity}
                            </span>

                          </td>

                          <td>

                            <span
                              className={`status-badge ${
                                rule.active
                                  ? "active"
                                  : "inactive"
                              }`}
                            >
                              {rule.active
                                ? "Active"
                                : "Inactive"}
                            </span>

                          </td>

                          <td>

                            <div className="table-actions">

                              <button
                                type="button"
                                className="icon-button edit"
                                title="Edit rule"
                                onClick={() =>
                                  handleEditRule(
                                    rule
                                  )
                                }
                              >
                                <Pencil size={18} />
                              </button>

                              <button
                                type="button"
                                className="icon-button delete"
                                title="Delete rule"
                                onClick={() =>
                                  deleteRule(
                                    rule.id
                                  )
                                }
                              >
                                <Trash2 size={18} />
                              </button>

                            </div>

                          </td>

                        </tr>

                      )
                    )

                  )}

                </tbody>

              </table>

            </div>

            <div className="table-footer" />

          </div>

        </section>

      </main>

      {/* =========================
          ADD / EDIT CATEGORY MODAL
      ========================= */}

      {showCategoryModal && (

        <div className="modal-overlay">

          <div className="modal-card category-modal">

            <div className="modal-header">

              <h2>
                {editingCategoryId
                  ? "Edit Category"
                  : "Add New Category"}
              </h2>

              <button
                type="button"
                className="modal-close"
                onClick={
                  closeCategoryModal
                }
              >
                <X size={22} />
              </button>

            </div>

            <form
              onSubmit={
                handleCategorySubmit
              }
            >

              <div className="form-field">

                <label>
                  Category Name{" "}
                  <span>*</span>
                </label>

                <input
                  type="text"
                  placeholder="Enter category name (e.g. Ambiguous)"
                  value={categoryForm.name}
                  maxLength={100}
                  onChange={(event) =>
                    setCategoryForm(
                      (current) => ({
                        ...current,
                        name:
                          event.target.value,
                      })
                    )
                  }
                  required
                />

                <div className="character-count">
                  {categoryForm.name.length}/100
                </div>

              </div>

              <div className="form-field">

                <label>
                  Description{" "}
                  <span>*</span>
                </label>

                <textarea
                  placeholder="Enter a brief description of this category"
                  value={
                    categoryForm.description
                  }
                  maxLength={500}
                  onChange={(event) =>
                    setCategoryForm(
                      (current) => ({
                        ...current,
                        description:
                          event.target.value,
                      })
                    )
                  }
                  required
                />

                <div className="character-count">
                  {
                    categoryForm.description
                      .length
                  }
                  /500
                </div>

              </div>

              <div className="form-field">

                <label>
                  Evaluation Mode{" "}
                  <span>*</span>
                </label>

                <select
                  value={
                    categoryForm.evaluationMode
                  }
                  onChange={(event) =>
                    setCategoryForm(
                      (current) => ({
                        ...current,
                        evaluationMode:
                          event.target.value,
                      })
                    )
                  }
                  required
                >

                  <option value="Issue">
                    Issue
                  </option>

                  <option value="Check">
                    Check
                  </option>

                </select>

                <div className="evaluation-mode-help">

                  <strong>
                    Issue:
                  </strong>{" "}
                  Rule match = Fail

                  <br />

                  <strong>
                    Check:
                  </strong>{" "}
                  Rule match = Pass

                </div>

              </div>

              <div className="modal-footer">

                <button
                  type="button"
                  className="secondary-button"
                  onClick={
                    closeCategoryModal
                  }
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="primary-button"
                >
                  {editingCategoryId
                    ? "Update Category"
                    : "Save Category"}
                </button>

              </div>

            </form>

          </div>

        </div>

      )}

      {/* =========================
          ADD / EDIT RULE MODAL
      ========================= */}

      {showRuleModal && (

        <div className="modal-overlay">

          <div className="modal-card rule-modal">

            <div className="modal-header">

              <h2>
                {editingRuleId
                  ? "Edit Rule"
                  : "Add New Rule"}
              </h2>

              <button
                type="button"
                className="modal-close"
                onClick={() => {
                  setEditingRuleId(null);
                  setShowRuleModal(false);
                }}
              >
                <X size={22} />
              </button>

            </div>

            <form
              onSubmit={handleRuleSubmit}
            >

              <div className="rule-form-grid">

                <div className="rule-form-main">

                  <div className="form-field">

                    <label>
                      Rule{" "}
                      <span>*</span>
                    </label>

                    <input
                      type="text"
                      placeholder="Enter rule (e.g. quickly)"
                      value={ruleForm.rule}
                      onChange={(event) =>
                        setRuleForm(
                          (current) => ({
                            ...current,
                            rule:
                              event.target.value,
                          })
                        )
                      }
                      required
                    />

                  </div>

                  <div className="form-field">

                    <label>
                      Description{" "}
                      <span>*</span>
                    </label>

                    <textarea
                      placeholder="Describe what this rule identifies"
                      value={
                        ruleForm.description
                      }
                      onChange={(event) =>
                        setRuleForm(
                          (current) => ({
                            ...current,
                            description:
                              event.target.value,
                          })
                        )
                      }
                      required
                    />

                  </div>

                  <div className="form-field">

                    <label>
                      Why it matters{" "}
                      <span>*</span>
                    </label>

                    <textarea
                      placeholder="Explain why this rule is important"
                      value={
                        ruleForm.whyItMatters
                      }
                      onChange={(event) =>
                        setRuleForm(
                          (current) => ({
                            ...current,
                            whyItMatters:
                              event.target.value,
                          })
                        )
                      }
                      required
                    />

                  </div>

                  <div className="form-field">

                    <label>
                      Recommendation{" "}
                      <span>*</span>
                    </label>

                    <textarea
                      placeholder="Suggested improvement or replacement"
                      value={
                        ruleForm.recommendation
                      }
                      onChange={(event) =>
                        setRuleForm(
                          (current) => ({
                            ...current,
                            recommendation:
                              event.target.value,
                          })
                        )
                      }
                      required
                    />

                  </div>

                </div>

                <div className="rule-form-side">

                  <div className="form-field">

                    <label>
                      Rule Type{" "}
                      <span>*</span>
                    </label>

                    <select
                      value={
                        ruleForm.ruleType
                      }
                      onChange={(event) =>
                        setRuleForm(
                          (current) => ({
                            ...current,
                            ruleType:
                              event.target.value,
                          })
                        )
                      }
                    >

                      <option value="Keyword">
                        Keyword
                      </option>

                      <option value="Pattern">
                        Pattern
                      </option>

                      <option value="Presence">
                        Presence
                      </option>

                    </select>

                  </div>

                  <div className="form-field">

                    <label>
                      Severity{" "}
                      <span>*</span>
                    </label>

                    <select
                      value={
                        ruleForm.severity
                      }
                      onChange={(event) =>
                        setRuleForm(
                          (current) => ({
                            ...current,
                            severity:
                              event.target.value,
                          })
                        )
                      }
                    >

                      <option value="Low">
                        Low
                      </option>

                      <option value="Medium">
                        Medium
                      </option>

                      <option value="High">
                        High
                      </option>

                    </select>

                  </div>

                  <div className="form-field">

                    <label>
                      Status
                    </label>

                    <label className="toggle-row">

                      <input
                        type="checkbox"
                        checked={
                          ruleForm.active
                        }
                        onChange={(event) =>
                          setRuleForm(
                            (current) => ({
                              ...current,
                              active:
                                event.target.checked,
                            })
                          )
                        }
                      />

                      <span className="toggle-slider" />

                      <span>
                        {ruleForm.active
                          ? "Active"
                          : "Inactive"}
                      </span>

                    </label>

                  </div>

                </div>

              </div>

              <div className="modal-footer">

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setEditingRuleId(null);
                    setShowRuleModal(false);
                  }}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  className="primary-button"
                >
                  {editingRuleId
                    ? "Update Rule"
                    : "Save Rule"}
                </button>

              </div>

            </form>

          </div>

        </div>

      )}

      {notification.open && (
        <div className="master-notification-overlay">
          <div
            className={`master-notification-card ${notification.type}`}
            role="alertdialog"
            aria-modal="true"
          >
            <div className="master-notification-icon">
              {notification.type === "success" ? (
                <CheckCircle2 size={28} />
              ) : (
                <AlertCircle size={28} />
              )}
            </div>

            <div className="master-notification-content">
              <h3>{notification.title}</h3>
              <p>{notification.message}</p>
            </div>

            <button
              type="button"
              className="master-notification-close"
              onClick={closeNotification}
            >
              OK
            </button>
          </div>
        </div>
      )}

      {deleteConfirmation.open && (
        <div className="master-notification-overlay">
          <div
            className="master-delete-confirm-card"
            role="dialog"
            aria-modal="true"
          >
            <div className="master-delete-confirm-icon">
              <Trash2 size={26} />
            </div>

            <div className="master-notification-content">
              <h3>{deleteConfirmation.title}</h3>
              <p>{deleteConfirmation.message}</p>
            </div>

            <div className="master-delete-confirm-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={closeDeleteConfirmation}
              >
                Cancel
              </button>
              <button
                type="button"
                className="master-delete-confirm-button"
                onClick={confirmDelete}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default MasterModulePage;