// Run once in DevTools Console on the AMIS CRM page you are signed in to.
// Downloads credentials locally; it does not send them to another website.
(() => {
  if (location.origin !== "https://amisapp.misa.vn") {
    throw new Error("Hay chay tren trang AMIS CRM dang dang nhap.");
  }
  const data = {};
  for (const key of ["token", "refresh_token", "companycode", ".ASPXAUTH"]) {
    const value = localStorage.getItem("AMIS.CRM_" + key);
    if (value && !["undefined", "null"].includes(value)) data[key] = value;
  }
  if (!data.companycode) {
    const cookie = document.cookie.split("; ").find(item => item.startsWith("CompanyCode="));
    if (cookie) data.companycode = decodeURIComponent(cookie.slice("CompanyCode=".length));
  }
  if (!data.token || !data.refresh_token || !data.companycode) {
    throw new Error("Khong tim thay du bo token/refresh_token/companycode. Chua tai file.");
  }
  const url = URL.createObjectURL(new Blob([JSON.stringify(data)], {type: "application/json"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = "amis_session.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  console.log("Da tai amis_session.json. Khong gui noi dung file vao chat.");
})();
