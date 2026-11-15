const isAllowedEmbedHost = (
  hostname: string,
  allowedHosts: readonly string[],
) => {
  const normalizedHost = hostname.toLowerCase();
  return allowedHosts.some((entry) => {
    if (entry.startsWith("*.")) {
      const base = entry.slice(2);
      // Match the backend exactly: a wildcard covers subdomains only. The apex
      // must be listed separately.
      return Boolean(base) && normalizedHost.endsWith(`.${base}`);
    }
    return normalizedHost === entry;
  });
};

export const stripDisallowedIframes = (
  sanitizedHtml: string,
  allowedHosts: readonly string[],
) => {
  const template = document.createElement("template");
  template.innerHTML = sanitizedHtml;
  for (const iframe of template.content.querySelectorAll("iframe")) {
    const src = iframe.getAttribute("src") ?? "";
    try {
      const url = new URL(src);
      if (
        url.protocol !== "https:" ||
        !isAllowedEmbedHost(url.hostname, allowedHosts)
      ) {
        iframe.remove();
      }
    } catch {
      iframe.remove();
    }
  }
  return template.innerHTML;
};

const iframeHostLabel = (src: string | null) => {
  try {
    return `Embedded content from ${new URL(src ?? "").hostname}`;
  } catch {
    return "Embedded content";
  }
};

export const prepareAllowedIframes = (sanitizedHtml: string) => {
  const template = document.createElement("template");
  template.innerHTML = sanitizedHtml;
  // Screen readers announce an iframe by its title. One the editor left untitled
  // takes the text of the closest heading before it in the same content (as in
  // "Message from the Dean" above a video), else the site it comes from.
  let lastHeading = "";
  for (const element of template.content.querySelectorAll("h1, h2, h3, h4, h5, h6, iframe")) {
    if (element.tagName !== "IFRAME") {
      lastHeading = element.textContent?.trim() ?? "";
      continue;
    }
    const iframe = element as HTMLIFrameElement;
    // Keep the original element in the DOM so CMS rules such as
    // `.video-container iframe` apply before the embed loads. Replacing the
    // element with a button breaks responsive wrappers that reserve their
    // aspect ratio with padding and absolutely position the iframe.
    iframe.setAttribute("loading", "lazy");
    if (!iframe.getAttribute("title")?.trim()) {
      iframe.setAttribute("title", lastHeading || iframeHostLabel(iframe.getAttribute("src")));
    }
  }
  return template.innerHTML;
};
