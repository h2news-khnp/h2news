// 수소 뉴스 아카이브 메인 스크립트

const newsListEl = document.getElementById("news-list");
const dateInput = document.getElementById("date");
const keywordInput = document.getElementById("keyword");
const sourceSelect = document.getElementById("source");
const applyBtn = document.getElementById("apply-filters");

let allNews = []; // JSON 전체 데이터 저장용

// 오늘 날짜를 YYYY-MM-DD 형식으로 반환
function getTodayString() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const d = String(now.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

// 뉴스 카드 렌더링
function renderNewsList(items) {
    newsListEl.innerHTML = "";

    if (!items || items.length === 0) {
        const div = document.createElement("div");
        div.className = "news-card";
        div.innerHTML = `
            <p>조건에 해당하는 뉴스가 없습니다.</p>
        `;
        newsListEl.appendChild(div);
        return;
    }

    items.forEach((item) => {
        const card = document.createElement("div");
        card.className = "news-card";

        const tagsHtml = (item.tags || [])
            .map((t) => `<span class="tag">${t}</span>`)
            .join("");

        card.innerHTML = `
            <div class="news-meta">
                <span class="news-date">${item.date || ""}</span>
                <span class="news-source">${item.source || ""}</span>
            </div>
            <h2 class="news-title">${item.title || ""}</h2>
            <p class="news-summary">${item.summary || ""}</p>
            <a class="news-link" href="${item.url || "#"}" target="_blank" rel="noopener noreferrer">
                원문 보기
            </a>
            <div class="news-tags">
                ${tagsHtml}
            </div>
        `;
        newsListEl.appendChild(card);
    });
}

// 필터 적용 로직
function applyFilters() {
    const dateValue = dateInput.value.trim();      // YYYY-MM-DD
    const keyword = keywordInput.value.trim();     // 검색어
    const source = sourceSelect.value.trim();      // 매체

    let filtered = [...allNews];

    if (dateValue) {
        filtered = filtered.filter((n) => n.date === dateValue);
    }

    if (source) {
        filtered = filtered.filter((n) => n.source === source);
    }

    if (keyword) {
        const lower = keyword.toLowerCase();
        filtered = filtered.filter((n) => {
            const title = (n.title || "").toLowerCase();
            const summary = (n.summary || "").toLowerCase();
            return title.includes(lower) || summary.includes(lower);
        });
    }

    renderNewsList(filtered);
}

// JSON 데이터 로드
async function loadNewsData(dateString) {
    const filePath = `data/${dateString}.json`;

    try {
        const res = await fetch(filePath);
        if (!res.ok) {
            throw new Error("파일 없음");
        }
        const data = await res.json();
        allNews = data;
        renderNewsList(allNews);
    } catch (e) {
        // 오늘 날짜 JSON이 없을 때: 안내 카드만 출력
        allNews = [];
        renderNewsList([]);
    }
}

// 초기화
function init() {
    const todayStr = getTodayString();

    // 날짜 필터 기본값을 오늘로 설정
    if (dateInput) {
        dateInput.value = todayStr;
    }

    // 오늘 날짜 기준 JSON 로드
    loadNewsData(todayStr);

    // 버튼 이벤트 연결
    if (applyBtn) {
        applyBtn.addEventListener("click", applyFilters);
    }
}

document.addEventListener("DOMContentLoaded", init);
