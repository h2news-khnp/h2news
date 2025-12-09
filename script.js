function loadNews() {
    const today = new Date().toISOString().slice(0, 10);
    const url = `data/${today}.json`;

    fetch(url)
        .then(res => res.json())
        .then(list => {
            const box = document.getElementById("news-container");
            box.innerHTML = "";

            list.forEach((a, idx) => {
                const id = a.url;  // 기사 URL을 고유 ID로 사용
                const likes = localStorage.getItem("like_" + id) || 0;

                const card = document.createElement("div");
                card.className = "card";

                card.innerHTML = `
                    <h2>${a.title}</h2>
                    <p>${a.summary.replace(/\n/g, "<br>")}</p>
                    <a href="${a.url}" target="_blank">원문 보기</a>
                    <img src="data/${a.image}" class="card-img">

                    <button class="like-btn" onclick="addLike('${id}', this)">
                        ❤️ 좋아요 <span>${likes}</span>
                    </button>
                `;

                box.appendChild(card);
            });
        });
}

function addLike(id, btn) {
    let count = parseInt(localStorage.getItem("like_" + id) || 0);
    count += 1;
    localStorage.setItem("like_" + id, count);

    btn.querySelector("span").innerText = count;
}

window.onload = loadNews;
