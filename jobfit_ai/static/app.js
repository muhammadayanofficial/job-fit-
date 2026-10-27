(function () {
  const textareas = document.querySelectorAll("textarea[maxlength]");

  textareas.forEach((textarea) => {
    const output = document.querySelector(`[data-count-for="${textarea.id}"]`);
    const updateCount = () => {
      if (output) output.textContent = `${textarea.value.length.toLocaleString()} characters`;
    };
    textarea.addEventListener("input", updateCount);
    updateCount();
  });

  const form = document.getElementById("analysis-form");
  const button = document.getElementById("analyze-button");
  if (form && button) {
    form.addEventListener("submit", () => {
      const resume = document.getElementById("resume_text").value.trim();
      const job = document.getElementById("job_description").value.trim();
      if (resume.length >= 80 && job.length >= 80) {
        button.disabled = true;
        button.querySelector("span:first-child").textContent = "Analyzing…";
        
      }
    });
  }

  const results = document.getElementById("analysis-results");
  if (results) {
    window.setTimeout(() => results.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
  }
})();
