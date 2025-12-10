import requests
from bs4 import BeautifulSoup
import json
import schedule
import time
from datetime import datetime
import os

# ==========================================
# 1. 설정 (키워드 및 타겟 URL)
# ==========================================
# 사용자 지정 키워드 리스트
KEYWORDS = [
    "수소", "연료전지", "그린수소", "청정수소", "블루수소", "원자력",
    "PAFC", "SOFC", "MCFC", "PEM", "재생", "배출권", "히트펌프", "도시가스", "구역전기", "PPA",
    "수전해", "전해조", "PEMEC", "AEM", "알카라인", "분산", "NDC", "핑크수소",
    "암모니아", "암모니아크래킹", "CCU", "CCUS", "기후부", "ESS", "배터리",
    "수소생산", "수소저장", "액화수소",
    "충전소", "수소버스", "수소차", "인프라",
    "한수원", "두산퓨얼셀", "한화임팩트", "현대차",
    "HPS", "HPC", "REC", "RPS"
]

JSON_FILENAME = "news_data.json"

# ==========================================
# 2. 크롤링 함수들
# ==========================================

def get_soup(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        return BeautifulSoup(res.text, 'html.parser')
    except Exception as e:
        print(f"   [Error] {url} 접속 실패: {e}")
        return None

def check_keywords(title):
    """제목에 키워드가 포함되어 있는지 확인"""
    found_keywords = [kw for kw in KEYWORDS if kw in title]
    return found_keywords

def crawl_energy_news():
    """에너지신문 크롤링"""
    print("   Running: 에너지신문...")
    results = []
    base_url = "https://www.energy-news.co.kr"
    url = "https://www.energy-news.co.kr/news/articleList.html?view_type=sm"
    
    soup = get_soup(url)
    if not soup: return results

    articles = soup.select('#section-list .type1 li')
    for article in articles:
        try:
            title_tag = article.select_one('h2.titles a')
            if not title_tag: continue
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            if not link.startswith('http'): link = base_url + link
            
            date_tag = article.select_one('em.info.dated')
            date = date_tag.get_text(strip=True) if date_tag else "-"

            category_tag = article.select_one('em.info.category')
            category = category_tag.get_text(strip=True) if category_tag else "기타"

            matched_kw = check_keywords(title)
            
            results.append({
                'source': '에너지신문',
                'category': category,
                'title': title,
                'link': link,
                'date': date,
                'keywords': matched_kw,
                'is_important': len(matched_kw) > 0
            })
        except: continue
    return results

def crawl_gas_news():
    """가스신문 크롤링"""
    print("   Running: 가스신문...")
    results = []
    base_url = "http://www.gasnews.com"
    url = "http://www.gasnews.com/news/articleList.html?view_type=sm" # 요약형
    
    soup = get_soup(url)
    if not soup: return results

    # 가스신문 구조 (에너지신문과 유사한 CMS 사용 가능성 높음, 일반적 구조 대응)
    articles = soup.select('#section-list .type1 li')
    if not articles: # 구조가 다를 경우 대비용 예비 선택자
        articles = soup.select('.article-list .list-block')

    for article in articles:
        try:
            title_tag = article.select_one('h2.titles a') or article.select_one('.list-titles a')
            if not title_tag: continue
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            if not link.startswith('http'): link = base_url + link
            
            date_tag = article.select_one('em.info.dated') or article.select_one('.byline span')
            date = date_tag.get_text(strip=True) if date_tag else "-"

            matched_kw = check_keywords(title)

            results.append({
                'source': '가스신문',
                'category': '가스/에너지',
                'title': title,
                'link': link,
                'date': date,
                'keywords': matched_kw,
                'is_important': len(matched_kw) > 0
            })
        except: continue
    return results

def crawl_electric_news():
    """전기신문 크롤링"""
    print("   Running: 전기신문...")
    results = []
    base_url = "https://www.electimes.com"
    url = "https://www.electimes.com/news/articleList.html?view_type=sm"
    
    soup = get_soup(url)
    if not soup: return results

    articles = soup.select('#section-list .type1 li')
    
    for article in articles:
        try:
            title_tag = article.select_one('h2.titles a')
            if not title_tag: continue
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            if not link.startswith('http'): link = base_url + link
            
            date_tag = article.select_one('em.info.dated')
            date = date_tag.get_text(strip=True) if date_tag else "-"
            
            category_tag = article.select_one('em.info.category')
            category = category_tag.get_text(strip=True) if category_tag else "전력"

            matched_kw = check_keywords(title)

            results.append({
                'source': '전기신문',
                'category': category,
                'title': title,
                'link': link,
                'date': date,
                'keywords': matched_kw,
                'is_important': len(matched_kw) > 0
            })
        except: continue
    return results

# ==========================================
# 3. 통합 실행 및 JSON 저장
# ==========================================
def job():
    print(f"\n[크롤링 시작] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    all_data = []
    
    all_data.extend(crawl_energy_news())
    all_data.extend(crawl_gas_news())
    all_data.extend(crawl_electric_news())
    
    # 중요 기사(키워드 포함)가 상단에 오도록 정렬
    all_data.sort(key=lambda x: x['is_important'], reverse=True)

    # JSON 저장
    output = {
        "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_count": len(all_data),
        "articles": all_data
    }
    
    with open(JSON_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
        
    print(f"[완료] {len(all_data)}건 수집 후 {JSON_FILENAME} 저장됨.")

# ==========================================
# 4. 스케줄러 설정
# ==========================================
if __name__ == "__main__":
    print("=== 뉴스 크롤러 자동화 시스템 시작 ===")
    print(f"타겟 키워드: {', '.join(KEYWORDS[:5])} ... 외 {len(KEYWORDS)-5}개")
    print("매일 08:00, 15:00에 자동으로 실행됩니다.")
    print("실행 중... (종료하려면 Ctrl+C)")

    # 최초 실행 (테스트용)
    job()

    # 스케줄 등록
    schedule.every().day.at("08:00").do(job)
    schedule.every().day.at("15:00").do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)
