#!/data/data/com.termux/files/usr/bin/python3
import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.tl.functions.messages import SaveDraftRequest
from telethon.tl.functions.users import GetFullUserRequest
from datetime import datetime, timezone
import signal

class TelegramDraftSender:
    def __init__(self):
        # Termux için data dizini
        self.data_dir = "/data/data/com.termux/files/home/telegram_drafts"
        self.ensure_data_dir()
        
        # API bilgileri
        self.api_id = 25680079 
        self.api_hash = '055d344ca63570ab232917a8292bba80'
        
        # Kullanıcıdan alınacak bilgiler
        self.phone_number = None
        self.group_url = None
        self.draft_message = None
        self.target_user_count = 45
        self.check_reaction_time = True
        
        # Termux optimizasyonları
        self.batch_size = 20
        self.request_delay = 1.0
        self.connection_timeout = 30
        
        self.client = None
        self.stats = {'sent': 0, 'failed': 0, 'skipped': 0}
        
        # Graceful shutdown için signal handler
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def ensure_data_dir(self):
        """Data dizinini oluştur"""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            print(f"✓ Data dizini hazır: {self.data_dir}")
        except Exception as e:
            print(f"⚠ Data dizini oluşturulamadı: {e}")
            self.data_dir = os.path.expanduser("~/telegram_drafts")
            os.makedirs(self.data_dir, exist_ok=True)
    
    def signal_handler(self, signum, frame):
        """Graceful shutdown"""
        print(f"\n🛑 Program sonlandırılıyor...")
        if self.client:
            asyncio.create_task(self.cleanup())
        sys.exit(0)
    
    def log_progress(self, message, level="INFO"):
        """Termux için optimize edilmiş loglama"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        symbols = {"INFO": "ℹ", "SUCCESS": "✓", "ERROR": "✗", "WARNING": "⚠"}
        symbol = symbols.get(level, "•")
        
        print(f"[{timestamp}] {symbol} {message}")
        
        # Log dosyasına da yaz
        try:
            log_file = os.path.join(self.data_dir, "app.log")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {level}: {message}\n")
        except:
            pass
    
    def get_user_input(self):
        """Kullanıcıdan bilgileri al"""
        print("\n📱 Telegram Draft Sender Ayarları")
        print("=" * 40)
        
        # Telefon numarası
        while True:
            phone = input("📞 Telefon numaranızı girin (+905xxxxxxxxx): ").strip()
            if phone.startswith('+90') and len(phone) >= 13:
                self.phone_number = phone
                break
            else:
                print("❌ Geçersiz format! Örnek: +905535350731")
        
        # Grup URL'si
        while True:
            group = input("📢 Grup URL'sini girin (https://t.me/grupadi): ").strip()
            if 't.me/' in group:
                self.group_url = group
                break
            else:
                print("❌ Geçersiz format! Örnek: https://t.me/busralgotrade")
        
        # Draft mesajı
        while True:
            message = input("💬 Gönderilecek mesaj (boş bırakılırsa '.'): ").strip()
            if message:
                self.draft_message = message
                break
            else:
                response = input("Boş mesaj gönderilsin mi? (e/h): ").strip().lower()
                if response in ['e', 'evet', 'y', 'yes']:
                    self.draft_message = "."
                    break
        
        # Hedef kullanıcı sayısı
        while True:
            try:
                count = input(f"🎯 Hedef kullanıcı sayısı (varsayılan: {self.target_user_count}): ").strip()
                if count:
                    self.target_user_count = int(count)
                if self.target_user_count > 0:
                    break
                else:
                    print("❌ Pozitif bir sayı girin!")
            except ValueError:
                print("❌ Geçerli bir sayı girin!")
        
        # Tepki süresi kontrolü
        while True:
            check = input("⏱ Tepki süresi kontrolü yapılsın mı? (e/h, varsayılan: e): ").strip().lower()
            if check in ['h', 'hayır', 'n', 'no']:
                self.check_reaction_time = False
                break
            elif check in ['', 'e', 'evet', 'y', 'yes']:
                self.check_reaction_time = True
                break
            else:
                print("❌ 'e' veya 'h' girin!")
        
        # Özet göster
        print(f"\n📋 Ayarlar Özeti:")
        print(f"📞 Telefon: {self.phone_number}")
        print(f"📢 Grup: {self.group_url}")
        print(f"💬 Mesaj: '{self.draft_message}'")
        print(f"🎯 Hedef: {self.target_user_count} kullanıcı")
        print(f"⏱ Tepki kontrolü: {'Açık' if self.check_reaction_time else 'Kapalı'}")
        
        while True:
            confirm = input("\n✅ Bu ayarlarla devam edilsin mi? (e/h): ").strip().lower()
            if confirm in ['e', 'evet', 'y', 'yes']:
                return True
            elif confirm in ['h', 'hayır', 'n', 'no']:
                print("❌ İşlem iptal edildi.")
                return False
            else:
                print("❌ 'e' veya 'h' girin!")
    
    async def create_client(self):
        """Client oluştur"""
        try:
            session_name = f"session_{self.phone_number.replace('+', '').replace(' ', '')}"
            session_path = os.path.join(self.data_dir, f"{session_name}.session")
            
            self.client = TelegramClient(
                session_path, 
                self.api_id, 
                self.api_hash,
                timeout=self.connection_timeout,
                connection_retries=3,
                retry_delay=2
            )
            
            # Bağlantı kurma - retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self.client.start(phone=self.phone_number)
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    self.log_progress(f"Bağlantı hatası, tekrar deneniyor... ({attempt+1}/{max_retries})", "WARNING")
                    await asyncio.sleep(5)
            
            self.log_progress(f"Client başarıyla oluşturuldu: {self.phone_number}", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_progress(f"Client oluşturulamadı: {e}", "ERROR")
            return False
    
    async def get_group_entity(self):
        """Grup entity alma"""
        try:
            if 't.me/' in self.group_url:
                username = self.group_url.split('t.me/')[-1]
                entity = await self.client.get_entity(username)
                self.log_progress(f"Grup bulundu: {entity.title}", "SUCCESS")
                return entity
        except Exception as e:
            self.log_progress(f"Grup bulunamadı: {e}", "ERROR")
            return None
    
    async def get_user_online_status(self, user_id):
        """Kullanıcının son çevrimiçi durumunu al"""
        try:
            full_user = await self.client(GetFullUserRequest(user_id))
            user_status = full_user.users[0].status
            
            if hasattr(user_status, 'was_online'):
                return user_status.was_online
            elif hasattr(user_status, 'expires'):
                return user_status.expires
            else:
                return None
                
        except Exception:
            return None
    
    async def should_send_to_user(self, user, message_date):
        """Kullanıcıya mesaj gönderilip gönderilmeyeceğini kontrol et"""
        if not self.check_reaction_time:
            return True
        
        try:
            last_online = await self.get_user_online_status(user.id)
            
            if last_online is None:
                return True
            
            # Timezone aware datetime'ları karşılaştır
            if message_date.tzinfo is None:
                message_date = message_date.replace(tzinfo=timezone.utc)
            if last_online.tzinfo is None:
                last_online = last_online.replace(tzinfo=timezone.utc)
            
            # 1 dakika tolerans
            time_diff = abs((message_date - last_online).total_seconds())
            
            if time_diff <= 60:
                self.stats['skipped'] += 1
                return False
            
            return True
            
        except Exception:
            return True
    
    async def get_reaction_users(self, group_entity):
        """Tepki veren kullanıcıları topla"""
        try:
            unique_users = set()
            processed_users = []
            offset_id = 0
            processed_messages = 0
            
            self.log_progress(f"Hedef kullanıcı sayısı: {self.target_user_count}")
            
            while len(unique_users) < self.target_user_count:
                messages = await self.client.get_messages(
                    group_entity, 
                    limit=50,
                    offset_id=offset_id
                )
                
                if not messages:
                    self.log_progress("Daha fazla mesaj bulunamadı", "WARNING")
                    break
                
                for message in messages:
                    processed_messages += 1
                    
                    if message.reactions and message.reactions.results:
                        for reaction in message.reactions.results:
                            try:
                                from telethon.tl.functions.messages import GetMessageReactionsListRequest
                                
                                reaction_users = await self.client(GetMessageReactionsListRequest(
                                    peer=group_entity,
                                    id=message.id,
                                    reaction=reaction.reaction,
                                    limit=min(reaction.count, 50)
                                ))
                                
                                for user in reaction_users.users:
                                    if user.id not in unique_users:
                                        if await self.should_send_to_user(user, message.date):
                                            unique_users.add(user.id)
                                            processed_users.append(user)
                                            
                                            if len(unique_users) >= self.target_user_count:
                                                self.log_progress(f"Hedef sayıya ulaşıldı: {len(unique_users)}", "SUCCESS")
                                                return processed_users[:self.target_user_count]
                                
                                await asyncio.sleep(self.request_delay)
                                
                            except Exception:
                                continue

                    offset_id = message.id
                
                # Progress update
                if processed_messages % 50 == 0:
                    self.log_progress(f"İşlenen mesaj: {processed_messages}, Bulunan kullanıcı: {len(unique_users)}")
                
                await asyncio.sleep(1)
            
            self.log_progress(f"Toplam {len(processed_users)} benzersiz kullanıcı bulundu")
            return processed_users
            
        except Exception as e:
            self.log_progress(f"Kullanıcı toplama hatası: {e}", "ERROR")
            return []
    
    async def send_saved_draft(self, user_id):
        """Draft gönder"""
        try:
            await self.client(SaveDraftRequest(
                peer=user_id,
                message=self.draft_message,
                entities=[],
                reply_to=None,
                no_webpage=False
            ))
            
            self.stats['sent'] += 1
            return True
            
        except Exception:
            self.stats['failed'] += 1
            return False
    
    def print_stats(self):
        """İstatistikleri göster"""
        total = self.stats['sent'] + self.stats['failed'] + self.stats['skipped']
        if total > 0:
            success_rate = (self.stats['sent'] / total) * 100
            print(f"\n📊 İstatistikler:")
            print(f"✓ Başarılı: {self.stats['sent']}")
            print(f"✗ Başarısız: {self.stats['failed']}")
            print(f"⏭ Atlanan: {self.stats['skipped']}")
            print(f"📈 Başarı oranı: {success_rate:.1f}%")
    
    async def process_users(self, users):
        """Kullanıcılara draft gönder"""
        total_users = len(users)
        success_count = 0
        
        self.log_progress(f"Toplam {total_users} kullanıcıya draft gönderiliyor...")
        
        # Batch processing
        for i in range(0, total_users, self.batch_size):
            batch = users[i:i + self.batch_size]
            
            for j, user in enumerate(batch):
                try:
                    if await self.send_saved_draft(user.id):
                        success_count += 1
                    
                    # Progress update
                    current = i + j + 1
                    if current % 10 == 0 or current == total_users:
                        self.log_progress(f"İlerleme: {current}/{total_users} - Başarılı: {success_count}")
                    
                    await asyncio.sleep(0.8)
                    
                except Exception:
                    continue
            
            # Batch arası dinlenme
            if i + self.batch_size < total_users:
                self.log_progress(f"Batch tamamlandı, 5 saniye bekleniyor...")
                await asyncio.sleep(5)
        
        self.log_progress(f"İşlem tamamlandı: {success_count}/{total_users} başarılı", "SUCCESS")
    
    async def cleanup(self):
        """Temizlik işlemleri"""
        if self.client:
            try:
                await self.client.disconnect()
                self.log_progress("Client bağlantısı kapatıldı", "SUCCESS")
            except:
                pass
        self.print_stats()
    
    async def run(self):
        """Ana çalıştırma fonksiyonu"""
        try:
            # Kullanıcıdan bilgileri al
            if not self.get_user_input():
                return
            
            self.log_progress("🚀 İşlem başlatılıyor...")
            
            # Client oluştur
            if not await self.create_client():
                return
            
            # Grup entity al
            group_entity = await self.get_group_entity()
            if not group_entity:
                return
            
            # Tepki veren kullanıcıları topla
            users = await self.get_reaction_users(group_entity)
            if not users:
                self.log_progress("Yeterli kullanıcı bulunamadı!", "WARNING")
                return
            
            # Draft'ları gönder
            await self.process_users(users)
            
            self.log_progress("Tüm işlemler tamamlandı! 🎉", "SUCCESS")
            
        except Exception as e:
            self.log_progress(f"Genel hata: {e}", "ERROR")
        
        finally:
            await self.cleanup()

def check_requirements():
    """Gereksinimleri kontrol et"""
    try:
        import telethon
        print("✓ Telethon yüklü")
        return True
    except ImportError:
        print("✗ Telethon yüklü değil")
        print("  Yüklemek için: pip install telethon")
        return False

async def main():
    print("🤖 Telegram Draft Sender - Interactive")
    print("=" * 40)
    
    if not check_requirements():
        return
    
    print("\n📋 Termux Kurulum:")
    print("1. pkg update && pkg upgrade")
    print("2. pkg install python")
    print("3. pip install telethon")
    
    input("\n📱 Devam etmek için Enter'a basın...")
    
    try:
        sender = TelegramDraftSender()
        await sender.run()
    except KeyboardInterrupt:
        print("\n👋 Kullanıcı tarafından iptal edildi")
    except Exception as e:
        print(f"\n💥 Beklenmeyen hata: {e}")

if __name__ == "__main__":
    asyncio.run(main())