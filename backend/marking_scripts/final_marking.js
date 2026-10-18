function captureInteractiveElements(options = {}) {
    const DEBUG_HIGHLIGHT = options.debugHighlight || false;
    const highlightColors = ['#FF0000', '#00FF00', '#0000FF', '#FFA500'];
    let elementIndex = 0;
    let highlightContainer = null;
  
    // --- PDF Detection ---
    // Check if the URL ends with ".pdf" or if the document contains an embed/iframe that likely shows a PDF.
    const url = window.location.href.toLowerCase();
    if (
      url.endsWith('.pdf') ||
      document.querySelector("embed[type*='pdf']") ||
      document.querySelector("iframe[src*='.pdf']")
    ) {
      // Create an overlay message for PDF detection
      const pdfOverlay = document.createElement("div");
      pdfOverlay.textContent = "PDF Detected";
      Object.assign(pdfOverlay.style, {
        position: "fixed",
        top: "10px",
        right: "10px",
        background: "rgba(255, 0, 0, 0.8)",
        color: "white",
        padding: "10px",
        zIndex: "2147483647",
        borderRadius: "5px",
        fontSize: "16px"
      });
      document.body.appendChild(pdfOverlay);
      console.log("PDF viewer detected.");
      
      // Return a minimal representation indicating PDF detection.
      const pdfElement = [{
        index: 0,
        type: "pdf",
        xpath: "",
        description: "PDF viewer detected",
        text: "",
        x: 0,
        y: 0
      }];
      console.log("Interactive DOM Tree:", pdfElement);
      return pdfElement;
    }
    // --- End PDF Detection ---
  
    // Create an overlay container for debug highlighting.
    if (DEBUG_HIGHLIGHT) {
        highlightContainer = document.createElement('div');
        highlightContainer.id = 'web-agent-highlight-container';
        Object.assign(highlightContainer.style, {
            position: 'absolute',
            pointerEvents: 'none',
            top: '0',
            left: '0',
            width: '100%',
            height: '100%',
            zIndex: '2147483647'
        });
        document.body.appendChild(highlightContainer);
    }
  
    // Compute an XPath for a given element.
    function getXPath(element) {
        if (!element) return '';
        if (element.id) return `//*[@id="${element.id}"]`;
  
        const parts = [];
        while (element && element.nodeType === Node.ELEMENT_NODE) {
            let index = 1;
            let sibling = element.previousSibling;
            while (sibling) {
                if (sibling.nodeType === Node.ELEMENT_NODE && sibling.tagName === element.tagName) {
                    index++;
                }
                sibling = sibling.previousSibling;
            }
            const tagName = element.tagName.toLowerCase();
            parts.unshift(index > 1 ? `${tagName}[${index}]` : tagName);
            element = element.parentNode;
        }
        return '/' + parts.join('/');
    }
  
    // Heuristic to determine if an element is interactive.
    function isInteractiveElement(element) {
        // Exclude elements that are hidden.
        if (!element.offsetWidth || !element.offsetHeight) return false;
        const style = window.getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
        }
  
        const interactiveTags = new Set(['a', 'button', 'input', 'select', 'textarea', 'summary']);
        const interactiveRoles = new Set([
            'button', 'link', 'textbox', 'checkbox', 'radio', 'combobox',
            'listbox', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'option',
            'switch', 'searchbox'
        ]);
  
        const tagName = element.tagName.toLowerCase();
        const role = element.getAttribute('role');
  
        if (interactiveTags.has(tagName)) return true;
        if (role && interactiveRoles.has(role.toLowerCase())) return true;
        if (element.onclick || element.getAttribute('onclick')) return true;
        if (element.getAttribute('tabindex') && element.getAttribute('tabindex') !== '-1') return true;
  
        return style.cursor === 'pointer';
    }
  
    // Determine a meaningful type for the element.
    function getElementType(element) {
      const tag = element.tagName.toLowerCase();
    
      // For <input> elements, return "button" for button types, else "input".
      if (tag === "input") {
        const inputType = element.getAttribute("type")
          ? element.getAttribute("type").toLowerCase()
          : "text";
        if (["button", "submit", "reset"].includes(inputType)) {
          return "button";
        }
        return "input";
      }
    
      // Prioritize the actual tag: if it is a <button>, always classify as "button"
      if (tag === "button") {
        return "button";
      }
    
      // Check the role attribute only if the tag is not already forcing a specific type.
      const role = element.getAttribute("role");
      if (role) {
        const r = role.toLowerCase();
    
        // Special handling for combobox
        if (r === "combobox") {
          if (element.hasAttribute("aria-autocomplete") || element.querySelector("input")) {
            return "input";
          }
          return "combobox";
        }
    
        // For a role of "link", only consider it a link if the element is an <a> tag.
        if (r === "link" && tag !== "a") {
          return tag;
        }
    
        // Return the role if it matches common interactive types.
        if (["button", "textbox", "checkbox", "radio", "listbox", "menuitem", "switch", "searchbox"].includes(r)) {
          return r;
        }
      }
    
      // For anchor tags, confirm it's a proper link.
      if (tag === "a" && element.hasAttribute("href")) {
        return "link";
      }
      if (tag === "select") return "select";
      if (tag === "textarea") return "textarea";
      if (element.onclick || element.getAttribute("onclick")) return "button";
    
      return tag;
    }
    
    // Generate a description for the element.
    function getElementDescription(element, type) {
        let desc = element.getAttribute("aria-label");
        if (desc && desc.trim().length > 0) return desc.trim();
        desc = element.getAttribute("title");
        if (desc && desc.trim().length > 0) return desc.trim();
  
        if (type === "link") {
            const txt = element.textContent.trim();
            return txt ? `Go to ${txt}` : "link";
        }
        if (type === "button") {
            const txt = element.textContent.trim();
            return txt ? txt : "button";
        }
        if (type === "input") {
            const placeholder = element.getAttribute("placeholder");
            if (placeholder && placeholder.trim().length > 0) {
                return placeholder.trim();
            }
            const val = element.value;
            if (val && val.trim().length > 0) {
                return val.trim();
            }
            return "input field";
        }
        const txt = element.textContent.trim();
        return txt ? txt : "";
    }
  
    // Retrieve relevant text for the element.
    function getElementText(element, type) {
        if (type === "input") {
            const value = element.value;
            if (value && value.trim().length > 0) {
                return value.trim();
            }
            const placeholder = element.getAttribute("placeholder");
            return placeholder ? placeholder.trim() : "";
        }
        return element.textContent.trim();
    }
  
    // Draw a colored overlay box on the element.
    function highlightElement(element, index) {
        if (!DEBUG_HIGHLIGHT || !highlightContainer) return;
        const rect = element.getBoundingClientRect();
        const color = highlightColors[index % highlightColors.length];
  
        const overlay = document.createElement('div');
        Object.assign(overlay.style, {
            position: 'absolute',
            border: `2px solid ${color}`,
            backgroundColor: `${color}22`,
            top: `${rect.top + window.scrollY}px`,
            left: `${rect.left + window.scrollX}px`,
            width: `${rect.width}px`,
            height: `${rect.height}px`
        });
  
        const label = document.createElement('div');
        Object.assign(label.style, {
            position: 'absolute',
            top: '-20px',
            left: '0',
            background: color,
            color: 'white',
            padding: '2px 4px',
            borderRadius: '3px',
            fontSize: '12px'
        });
        label.textContent = index;
        overlay.appendChild(label);
  
        highlightContainer.appendChild(overlay);
    }
  
    // Use a TreeWalker to traverse the document and capture interactive elements.
    // Guard against pages that are still loading or have no body yet; the caller
    // treats an empty list as "no interactive elements on this page".
    if (!document.body) {
        console.log("No document.body yet, returning no interactive elements.");
        return [];
    }
    const capturedElements = [];
    const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_ELEMENT,
        {
            acceptNode: (node) =>
                isInteractiveElement(node)
                    ? NodeFilter.FILTER_ACCEPT
                    : NodeFilter.FILTER_SKIP
        }
    );
  
    while (walker.nextNode()) {
        const current = walker.currentNode;
        if (capturedElements.some((el) => el.contains(current))) {
            continue;
        }
        capturedElements.push(current);
        highlightElement(current, elementIndex);
        elementIndex++;
    }
  
    const result = capturedElements.map((el, idx) => {
        const rect = el.getBoundingClientRect();
        const type = getElementType(el);
        return {
            index: idx,
            type: type,
            xpath: getXPath(el),
            description: getElementDescription(el, type),
            text: getElementText(el, type),
            x: rect.left + window.scrollX,
            y: rect.top + window.scrollY
        };
    });
    console.log("Interactive DOM Tree:", result);
    return result;
  }

    // --- Usage Example ---
    const interactiveDomTree = captureInteractiveElements({ debugHighlight: true });








    