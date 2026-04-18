const API_BASE = (window.location.protocol === "file:" || window.location.hostname === "localhost")
    ? "http://localhost:8000/api" 
    : "/api";

let currentOrder = null;
let pollInterval = null;

document.addEventListener("DOMContentLoaded", () => {
    const urlParams = new URLSearchParams(window.location.search);
    const productId = urlParams.get('id');
    const orderId = urlParams.get('order_id');
    
    if (orderId) {
        // Direct to payment if we already have an order (e.g., from scanning a bridge QR)
        loadOrderById(orderId);
    } else if (productId) {
        fetchProduct(productId);
    } else {
        document.getElementById("product-name").innerText = "请从店铺首页选择商品";
        document.getElementById("buy-btn").style.display = "none";
    }
});

async function loadOrderById(id) {
    try {
        const res = await fetch(`${API_BASE}/orders/${id}/status`);
        const data = await res.json();
        // Since get_order_status returns status and content, we need to fetch full order details if we want amount
        // But for simplicity, we'll assume we can get order info
        const orderRes = await fetch(`${API_BASE}/orders/${id}/details`);
        currentOrder = await orderRes.json();
        
        if (currentOrder.status === "paid") {
            showSuccess(currentOrder.content);
        } else {
            showPayment();
            startPolling();
        }
    } catch (err) {
        console.error("Failed to load order", err);
    }
}

async function fetchProduct(id) {
    try {
        const res = await fetch(`${API_BASE}/products/${id}`);
        const product = await res.json();
        
        document.getElementById("product-name").innerText = product.name;
        document.getElementById("product-desc").innerText = product.description || "全自动秒发货";
        document.getElementById("product-price").innerText = product.price.toFixed(2);

        // Show Back to Store link
        if (product.merchant_id) {
            const backDiv = document.getElementById("back-to-store");
            const link = document.getElementById("store-link");
            backDiv.style.display = "block";
            link.href = `store.html?merchant=${product.merchant_id}`;
        }
    } catch (err) {
        console.error("Failed to fetch product", err);
    }
}

async function createOrder() {
    const urlParams = new URLSearchParams(window.location.search);
    const productId = urlParams.get('id');
    
    try {
        const res = await fetch(`${API_BASE}/orders?product_id=${productId}`, {
            method: "POST"
        });
        
        if (res.status === 403) {
            const data = await res.json();
            alert(`无法下单：该商家佣金余额不足，请联系商家处理。`);
            return;
        }

        if (!res.ok) throw new Error("Order creation failed");

        currentOrder = await res.json();
        showPayment();
        startPolling();
    } catch (err) {
        alert("创建订单失败，请稍后刷新重试");
    }
}

function showPayment() {
    document.getElementById("product-card").style.display = "none";
    document.getElementById("payment-card").style.display = "block";
    document.getElementById("pay-amount").innerText = currentOrder.amount.toFixed(2);
    document.getElementById("qr-image").src = currentOrder.qr_code;
    
    // Setup Alipay One-Click Jump
    const alipayBtn = document.getElementById("alipay-jump-btn");
    if (currentOrder.alipay_url) {
        alipayBtn.style.display = "block";
        alipayBtn.onclick = () => {
            copyToClipboard(currentOrder.amount.toFixed(2));
            window.location.href = currentOrder.alipay_url;
        };
    } else {
        alipayBtn.style.display = "none";
    }

    // Auto-copy amount when entering payment card to help the user
    copyToClipboard(currentOrder.amount.toFixed(2), false);

    // Start expiration countdown
    let timeLeft = 300;
    const interval = setInterval(() => {
        timeLeft--;
        if (timeLeft <= 0) {
            clearInterval(interval);
            alert("订单已过期，请刷新页面重新下单");
            location.reload();
        }
    }, 1000);
}

function copyToClipboard(text, showToast = true) {
    const tempInput = document.createElement("input");
    tempInput.value = text;
    document.body.appendChild(tempInput);
    tempInput.select();
    document.execCommand("copy"); // Fallback for older browsers
    document.body.removeChild(tempInput);
    
    // Modern API try
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text);
    }
    
    if (showToast) {
        const toast = document.getElementById("copy-toast");
        if (toast) {
            toast.style.display = "block";
            setTimeout(() => { toast.style.display = "none"; }, 2000);
        }
    }
}

function startPolling() {
    // Clear any existing interval
    if (pollInterval) clearInterval(pollInterval);

    // Poll every 3 seconds
    pollInterval = setInterval(async () => {
        if (!currentOrder) return;

        try {
            const res = await fetch(`${API_BASE}/orders/${currentOrder.order_id}/status`);
            const data = await res.json();

            if (data.status === "paid") {
                clearInterval(pollInterval);
                showSuccess(data.content);
            } else if (data.status === "expired") {
                clearInterval(pollInterval);
                alert("支付超时，请返回重新下单");
                location.reload();
            }
        } catch (err) {
            console.error("Polling error", err);
        }
    }, 3000);
}

// Keep the manual button for legacy support or faster feedback
async function confirmPayment() {
    // In the new system, this usually just waits or checks immediately
    const btn = document.getElementById("confirm-btn");
    btn.innerText = "正在核对中...";
    btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/orders/${currentOrder.order_id}/status`);
        const data = await res.json();
        if (data.status === "paid") {
            showSuccess(data.content);
        } else {
            alert("尚未检测到支付，请确保已成功扫码并等待几秒。");
            btn.innerText = "我已支付";
            btn.disabled = false;
        }
    } catch (err) {
        btn.innerText = "我已支付";
        btn.disabled = false;
    }
}

function showSuccess(content) {
    document.getElementById("payment-card").style.display = "none";
    document.getElementById("delivery-card").style.display = "block";
    document.getElementById("delivery-content").innerText = content;
}

function showProduct() {
    if (pollInterval) clearInterval(pollInterval);
    document.getElementById("payment-card").style.display = "none";
    document.getElementById("product-card").style.display = "block";
}
