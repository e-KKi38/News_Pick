import flet as ft
from deep_translator import GoogleTranslator
import aiohttp
import asyncio
from functools import partial
import signal
import sys
import json
import os
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from config import FAVORITES_FILE, BASE_URL

# データクラスの定義
@dataclass
class NewsArticle:
    title: str
    description: str
    translated_title: str = ""
    translated_description: str = ""
    is_read: bool = False

class NewsState:
    def __init__(self):
        self.current_page: int = 0
        self.articles_per_page: int = 10
        self.current_country: str = 'jp'
        self.favorites: List[Dict] = []
        self.all_articles: List[ft.Container] = []

class NewsApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.state = NewsState()
        self.setup_signal_handlers()  # シグナルハンドラのセットアップを追加
        self.setup_page()
        self.load_favorites()
        self.init_components()

    def setup_signal_handlers(self):
        """シグナルハンドラの設定"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, sig, frame):
        """シグナルハンドリング処理"""
        print('プログラムを終了します')
        sys.exit(0)

    def setup_page(self):
        """ページの基本設定"""
        self.page.title = "グローバルニュースアプリ"
        self.page.vertical_alignment = ft.MainAxisAlignment.START

    def load_favorites(self):
        """お気に入りの読み込み"""
        if os.path.exists(FAVORITES_FILE):
            try:
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    self.state.favorites = json.load(f)
            except json.JSONDecodeError as e:
                print(f"お気に入りファイルの読み込みエラー: {e}")
                self.state.favorites = []
            except Exception as e:
                print(f"予期せぬエラー: {e}")
                self.state.favorites = []

    def save_favorites(self):
        """お気に入りの保存"""
        with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.state.favorites, f, ensure_ascii=False, indent=2)

    def init_components(self):
        """UIコンポーネントの初期化"""
        # ステータス表示用コンポーネント
        self.status_text = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        self.loading_container = self.create_loading_container()
        self.headlines_list = ft.ListView(expand=True)
        
        self.pagination_text = ft.Text("", size=14)
        self.pagination_row = self.create_pagination_row()

        # ローディングインジケーター
        self.loading_container = self.create_loading_container()
        
        # ニュースリスト
        self.headlines_list = ft.ListView(expand=True)
        
        # ページネーション
        self.pagination_row = self.create_pagination_row()
        
        # タブ
        self.tabs = self.create_tabs()
        
        # ヘッダー
        self.header_row = self.create_header_row()

        # ページにコンポーネントを追加
        self.page.add(
            self.header_row,
            self.tabs,
            self.loading_container,
            self.headlines_list,
            self.pagination_row
        )

    def create_loading_container(self) -> ft.Container:
        """ローディングインジケーターの作成"""
        return ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(),
                    ft.Text("読み込み中...", size=16)
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            alignment=ft.alignment.center,
            visible=False,
        )

    def create_pagination_row(self) -> ft.Row:
        """ページネーションボタンの作成"""
        return ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK, 
                    on_click=lambda _: self.change_page(-1)
                ),
                self.pagination_text,  # pagination_textを追加
                ft.IconButton(
                    icon=ft.Icons.ARROW_FORWARD, 
                    on_click=lambda _: self.change_page(1)
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            visible=False,
        )

    def create_header_row(self) -> ft.Row:
        """ヘッダー行の作成"""
        return ft.Row(
            [
                self.status_text,
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="最新のニュースを取得",
                    on_click=self.refresh_news
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def create_tabs(self) -> ft.Tabs:
        """タブの作成"""
        return ft.Tabs(
            selected_index=0,
            on_change=self.handle_tab_change,
            tabs=[
                ft.Tab(text=name) for name in self.countries.values()
            ] + [ft.Tab(text="お気に入り")]
        )

    async def handle_tab_change(self, e):
        """タブ切り替え時の処理"""
        selected_index = e.control.selected_index
        if selected_index is None:
            return
            
        if selected_index >= len(self.countries):
            await self.display_favorites()
        else:
            country_codes = list(self.countries.keys())
            if selected_index < len(country_codes):
                self.state.current_country = country_codes[selected_index]
                await self.fetch_headlines(self.state.current_country)

    async def refresh_news(self, e):
        """ニュースの更新"""
        await self.fetch_headlines(self.state.current_country)

    async def fetch_headlines(self, country_code: str):
        """ニュースの取得"""
        try:
            self.show_loading(True)
            self.update_status("ニュースを取得中...")
            
            self.headlines_list.controls.clear()
            self.state.all_articles.clear()
            self.headlines_list.update()
            
            url = BASE_URL.format(country_code)
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        await self.process_news_response(await response.json(), country_code)
                    else:
                        self.update_status(f"ニュースの取得に失敗しました。(エラーコード: {response.status})")
        except Exception as e:
            self.update_status(f"エラーが発生しました: {str(e)}")
        finally:
            self.show_loading(False)

    async def process_news_response(self, data: Dict, country_code: str):
        """ニュース応答の処理"""
        articles = data.get('articles', [])
        if not articles:
            self.update_status(f"{self.countries[country_code]}のニュースが見つかりませんでした。")
            return

        translator = GoogleTranslator(source='auto', target='ja')
        self.update_status(f"{len(articles)}件のニュースを取得しました")
        
        for article in articles:
            translated_article = await self.translate_article(article, translator)
            article_container = self.create_article_container(article, translated_article)
            self.state.all_articles.append(article_container)
        
        self.pagination_row.visible = len(self.state.all_articles) > self.state.articles_per_page
        self.display_articles(0)

    async def translate_article(self, article: Dict, translator: GoogleTranslator) -> NewsArticle:
        """記事の翻訳"""
        title = article.get('title', '')
        description = article.get('description', '')
        
        translated_title = await self.translate_text(translator, title) if title else "タイトルなし"
        translated_description = await self.translate_text(translator, description) if description else "内容なし"
        
        return NewsArticle(
            title=title,
            description=description,
            translated_title=translated_title,
            translated_description=translated_description
        )

    async def translate_text(self, translator: GoogleTranslator, text: str) -> str:
        """テキストの翻訳"""
        if not text:
            return ""
        try:
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(None, partial(translator.translate, text=text))
            return translated
        except Exception as e:
            print(f"翻訳エラー: {str(e)}")
            return text

    def create_article_container(self, raw_article: Dict, article: NewsArticle) -> ft.Container:
        """記事コンテナの作成"""
        container = ft.Container(
            content=ft.Column([
                ft.Text(
                    article.translated_title,
                    size=16,
                    weight=ft.FontWeight.BOLD
                ),
                ft.Text(
                    article.translated_description,
                    size=14
                ),
                ft.Row([
                    ft.IconButton(
                        icon=self.get_favorite_icon(raw_article),
                        on_click=lambda e: self.handle_favorite_click(e, raw_article)
                    )
                ])
            ]),
            padding=10,
            border=ft.border.all(1, ft.Colors.GREY_400),
            border_radius=10,
            margin=ft.margin.only(bottom=10)
            # bgcolor条件を削除
        )
        return container

    def get_favorite_icon(self, article: Dict) -> str:
        """お気に入りアイコンの取得"""
        return ft.Icons.FAVORITE if self.is_favorite(article) else ft.Icons.FAVORITE_BORDER

    def is_favorite(self, article: Dict) -> bool:
        """記事がお気に入りかどうかを確認"""
        return any(
            fav.get('title') == article.get('title') and 
            fav.get('description') == article.get('description') 
            for fav in self.state.favorites
        )

    def handle_favorite_click(self, e: ft.ControlEvent, article: Dict):
        """お気に入りクリック時の処理"""
        if self.is_favorite(article):
            self.state.favorites.remove(article)
        else:
            self.state.favorites.append(article)
        
        self.save_favorites()
        e.control.icon = self.get_favorite_icon(article)
        e.control.update()

        # お気に入りタブ表示中の場合は更新
        if self.tabs.selected_index == len(self.countries):
            asyncio.create_task(self.display_favorites())

    async def display_favorites(self):
        """お気に入り記事の表示"""
        self.headlines_list.controls.clear()
        self.state.all_articles.clear()
        
        if not self.state.favorites:
            self.headlines_list.controls.append(
                ft.Container(
                    content=ft.Text(
                        "お気に入りのニュースはありません",
                        size=16,
                        color=ft.Colors.GREY
                    ),
                    padding=10
                )
            )
        else:
            translator = GoogleTranslator(source='auto', target='ja')
            for article in self.state.favorites:
                translated_article = await self.translate_article(article, translator)
                article_container = self.create_article_container(article, translated_article)
                self.state.all_articles.append(article_container)
            
            self.display_articles(0)
        
        self.headlines_list.update()

    def display_articles(self, page_num: int):
        """記事の表示"""
        self.state.current_page = page_num
        start_idx = page_num * self.state.articles_per_page
        end_idx = start_idx + self.state.articles_per_page
        current_articles = self.state.all_articles[start_idx:end_idx]
        
        total_pages = (len(self.state.all_articles) + self.state.articles_per_page - 1) // self.state.articles_per_page
        
        self.headlines_list.controls.clear()
        for article in current_articles:
            self.headlines_list.controls.append(article)
        
        # ページ情報を表示
        self.pagination_text.value = f"ページ {page_num + 1}/{total_pages}"
        self.pagination_text.update()
        self.headlines_list.update()

    def change_page(self, delta: int):
        """ページの切り替え"""
        new_page = self.state.current_page + delta
        if 0 <= new_page < (len(self.state.all_articles) + self.state.articles_per_page - 1) // self.state.articles_per_page:
            self.display_articles(new_page)

    def update_status(self, message: str):
        """ステータスメッセージの更新"""
        self.status_text.value = message
        self.status_text.update()

    def show_loading(self, show: bool):
        """ローディング表示の切り替え"""
        self.loading_container.visible = show
        self.loading_container.update()

    async def check_for_updates(self):
        """定期的なニュース更新"""
        while True:
            await asyncio.sleep(300)  # 5分ごとに更新
            await self.fetch_headlines(self.state.current_country)
            self.page.show_snack_bar(
                ft.SnackBar(content=ft.Text("新しいニュースが利用可能です"))
            )

    @property
    def countries(self):
        """サポートする国のリスト"""
        return {
            'jp': '日本',
            'us': 'アメリカ',
            'gb': 'イギリス',
            'fr': 'フランス',
            'de': 'ドイツ',
            'kr': '韓国',
            'cn': '中国'
        }

async def main(page: ft.Page):
    app = NewsApp(page)
    # 初期表示
    await app.fetch_headlines('jp')

if __name__ == "__main__":
    ft.app(target=main)