
#!/data/data/com.termux/files/usr/bin/python3
import asyncio
import os
import sys
import json
from telethon import TelegramClient
from telethon.tl.functions.messages import SaveDraftRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.errors import UserPrivacyRestrictedError, UserBlockedError, PeerFloodError
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
        self.group_identifier = None  # URL veya grup ismi
        self.draft_message = None
        self.target_user_count = 45
        self.check_reaction_time = True
        self.skip_admins = True  # Yöneticileri atla
        self.include_message_senders = True  # YENİ: Mesaj gönderenleri dahil et
        
        # Termux optimizasyonları
        self.batch_size = 20
        self.request_delay = 1.0
        self.connection_timeout = 30
        
        self.client = None
        self.stats = {
            'sent': 0, 
            'failed': 0, 
            'skipped': 0, 
            'blacklisted': 0,
            'admin_skipped': 0,  # Yönetici olduğu için atlanan
            'blocked_skipped': 0,  # Engelleme nedeniyle atlanan
            'reaction_users': 0,  # Tepki veren kullanıcılar
            'message_senders': 0  # Mesaj gönderen kullanıcılar
        }
        
        # Merkezi blacklist dosya yolu (telefon numarasına özel değil)
        self.blacklist_file = os.path.join(self.data_dir, "global_blacklist.json")
        self.blacklist = set()
        self.load_blacklist()  # Program başında blacklist'i yükle
        
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
    
    def setup_blacklist_file(self):
        """Blacklist dosyası zaten __init__'te ayarlandı - gereksiz"""
        pass
    
    def load_blacklist(self):
        """Blacklist'i dosyadan yükle"""
        try:
            if os.path.exists(self.blacklist_file):
                with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.blacklist = set(data.get('user_ids', []))
                    self.log_progress(f"Global Blacklist yüklendi: {len(self.blacklist)} kullanıcı", "SUCCESS")
            else:
                self.blacklist = set()
                self.log_progress("Yeni Global Blacklist oluşturuldu", "INFO")
        except Exception as e:
            self.log_progress(f"Blacklist yüklenemedi: {e}", "WARNING")
            self.blacklist = set()
    
    def save_blacklist(self):
        """Blacklist'i dosyaya kaydet"""
        try:
            blacklist_data = {
                'user_ids': list(self.blacklist),
                'last_updated': datetime.now().isoformat(),
                'total_count': len(self.blacklist)
            }
            
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump(blacklist_data, f, ensure_ascii=False, indent=2)
            
            self.log_progress(f"Global Blacklist kaydedildi: {len(self.blacklist)} kullanıcı", "SUCCESS")
        except Exception as e:
            self.log_progress(f"Global Blacklist kaydedilemedi: {e}", "ERROR")
    
    def add_to_blacklist(self, user_id):
        """Kullanıcıyı blacklist'e ekle"""
        self.blacklist.add(user_id)
    
    def is_blacklisted(self, user_id):
        """Kullanıcının blacklist'te olup olmadığını kontrol et"""
        return user_id in self.blacklist
    
    def show_blacklist_stats(self):
        """Blacklist istatistiklerini göster"""
        if self.blacklist_file and os.path.exists(self.blacklist_file):
            try:
                with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    last_updated = data.get('last_updated', 'Bilinmiyor')
                    
                print(f"\n🚫 Global Blacklist İstatistikleri:")
                print(f"📊 Toplam engellenen kullanıcı: {len(self.blacklist)}")
                print(f"🕒 Son güncelleme: {last_updated}")
                print(f"📍 Dosya konumu: {self.blacklist_file}")
                
            except Exception as e:
                self.log_progress(f"Blacklist stats okunamadı: {e}", "WARNING")
    
    def clear_blacklist_option(self):
        """Blacklist temizleme seçeneği"""
        if len(self.blacklist) > 0:
            print(f"\n🚫 Mevcut Global Blacklist: {len(self.blacklist)} kullanıcı")
            print("⚠ Bu liste TÜM telefon numaraları için geçerlidir!")
            while True:
                clear = input("Global Blacklist'i temizlemek ister misiniz? (e/h): ").strip().lower()
                if clear in ['e', 'evet', 'y', 'yes']:
                    self.blacklist.clear()
                    self.save_blacklist()
                    self.log_progress("Global Blacklist temizlendi", "SUCCESS")
                    break
                elif clear in ['h', 'hayır', 'n', 'no']:
                    break
                else:
                    print("❌ 'e' veya 'h' girin!")
    
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
    
    async def is_user_admin(self, group_entity, user_id):
        """Kullanıcının grup yöneticisi olup olmadığını kontrol et"""
        try:
            participant = await self.client(GetParticipantRequest(
                channel=group_entity,
                participant=user_id
            ))
            
            # Yönetici veya grup sahibi mi kontrol et
            is_admin = isinstance(participant.participant, (ChannelParticipantAdmin, ChannelParticipantCreator))
            
            if is_admin:
                self.log_progress(f"Yönetici tespit edildi: {user_id}", "INFO")
            
            return is_admin
            
        except Exception as e:
            # Hata durumunda false döndür (normal kullanıcı varsay)
            return False
    
    async def can_send_message_to_user(self, user_id):
        """Kullanıcıya mesaj gönderilip gönderilemeyeceğini kontrol et"""
        try:
            # Kullanıcının tam bilgilerini al
            full_user = await self.client(GetFullUserRequest(user_id))
            user = full_user.users[0]
            
            # Kullanıcı beni engellemiş mi?
            if hasattr(user, 'blocked') and user.blocked:
                return False, "user_blocked_me"
            
            # Ben kullanıcıyı engellemiş miyim?
            if hasattr(full_user.full_user, 'blocked') and full_user.full_user.blocked:
                return False, "i_blocked_user"
            
            return True, "can_send"
            
        except UserBlockedError:
            return False, "user_blocked_me"
        except Exception as e:
            return True, "unknown_error"
    
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
        
        # Blacklist durumunu göster (telefon numarasından bağımsız)
        self.show_blacklist_stats()
        self.clear_blacklist_option()
        
        # Grup URL'si veya ismi - GÜNCELLENDİ
        while True:
            group = input("📢 Grup URL'sini veya grup ismini girin:\n" + 
                         "   URL için: https://t.me/grupadi\n" +
                         "   İsim için: Grup Adı\n" +
                         "   Giriş: ").strip()
            if group:
                self.group_identifier = group
                break
            else:
                print("❌ Boş bırakılamaz!")
        
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
        
        # Mesaj gönderenleri dahil etme kontrolü - YENİ
        while True:
            include_senders = input("📝 Mesaj gönderen kullanıcılar da dahil edilsin mi? (e/h, varsayılan: e): ").strip().lower()
            if include_senders in ['h', 'hayır', 'n', 'no']:
                self.include_message_senders = False
                break
            elif include_senders in ['', 'e', 'evet', 'y', 'yes']:
                self.include_message_senders = True
                break
            else:
                print("❌ 'e' veya 'h' girin!")
        
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
        
        # Yönetici atlama kontrolü
        while True:
            skip_admin = input("👑 Grup yöneticileri atlanسın mı? (e/h, varsayılan: e): ").strip().lower()
            if skip_admin in ['h', 'hayır', 'n', 'no']:
                self.skip_admins = False
                break
            elif skip_admin in ['', 'e', 'evet', 'y', 'yes']:
                self.skip_admins = True
                break
            else:
                print("❌ 'e' veya 'h' girin!")
        
        # Grup türü belirleme
        group_type = "URL" if ('t.me/' in self.group_identifier or 'telegram.me/' in self.group_identifier) else "İsim"
        
        # Özet göster
        print(f"\n📋 Ayarlar Özeti:")
        print(f"📞 Telefon: {self.phone_number}")
        print(f"📢 Grup ({group_type}): {self.group_identifier}")
        print(f"💬 Mesaj: '{self.draft_message}'")
        print(f"🎯 Hedef: {self.target_user_count} kullanıcı")
        print(f"📝 Mesaj gönderenler: {'Dahil' if self.include_message_senders else 'Hariç'}")
        print(f"⏱ Tepki kontrolü: {'Açık' if self.check_reaction_time else 'Kapalı'}")
        print(f"👑 Yönetici atlama: {'Açık' if self.skip_admins else 'Kapalı'}")
        print(f"🚫 Global Blacklist: {len(self.blacklist)} kullanıcı")
        
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
        """Grup entity alma - URL ve isim desteği"""
        try:
            # URL kontrolü
            if 't.me/' in self.group_identifier or 'telegram.me/' in self.group_identifier:
                # URL'den username çıkar
                if 't.me/' in self.group_identifier:
                    username = self.group_identifier.split('t.me/')[-1]
                else:
                    username = self.group_identifier.split('telegram.me/')[-1]
                
                # URL parametrelerini temizle
                username = username.split('?')[0].split('#')[0]
                
                self.log_progress(f"URL'den grup aranıyor: @{username}", "INFO")
                entity = await self.client.get_entity(username)
                
            else:
                # Grup ismi ile arama
                self.log_progress(f"İsimle grup aranıyor: {self.group_identifier}", "INFO")
                
                # Önce dialogları kontrol et
                async for dialog in self.client.iter_dialogs():
                    if (dialog.title and 
                        self.group_identifier.lower() in dialog.title.lower() and
                        dialog.is_group):
                        
                        self.log_progress(f"Grup bulundu (dialog): {dialog.title}", "SUCCESS")
                        return dialog.entity
                
                # Dialog'da bulunamadıysa direkt entity olarak dene
                entity = await self.client.get_entity(self.group_identifier)
            
            self.log_progress(f"Grup bulundu: {entity.title}", "SUCCESS")
            return entity
            
        except Exception as e:
            self.log_progress(f"Grup bulunamadı: {e}", "ERROR")
            
            # Alternatif arama önerileri
            if 't.me/' not in self.group_identifier and 'telegram.me/' not in self.group_identifier:
                self.log_progress("💡 Öneriler:", "INFO")
                self.log_progress("• Grup ismini tam olarak yazın", "INFO")
                self.log_progress("• Grubun herkese açık olduğundan emin olun", "INFO")
                self.log_progress("• Grup URL'sini kullanmayı deneyin", "INFO")
            
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
    
    async def should_send_to_user(self, user, message_date, group_entity):
        """Kullanıcıya mesaj gönderilip gönderilmeyeceğini kontrol et"""
        # Önce blacklist kontrolü
        if self.is_blacklisted(user.id):
            self.stats['blacklisted'] += 1
            return False, "blacklisted"
        
        # Yönetici kontrolü
        if self.skip_admins:
            if await self.is_user_admin(group_entity, user.id):
                self.stats['admin_skipped'] += 1
                return False, "admin"
        
        # Engelleme durumu kontrolü
        can_send, reason = await self.can_send_message_to_user(user.id)
        if not can_send:
            if reason == "user_blocked_me":
                self.stats['blocked_skipped'] += 1
                return False, "user_blocked_me"
            elif reason == "i_blocked_user":
                self.stats['blocked_skipped'] += 1
                return False, "i_blocked_user"
        
        # Tepki süresi kontrolü
        if not self.check_reaction_time:
            return True, "ok"
        
        try:
            last_online = await self.get_user_online_status(user.id)
            
            if last_online is None:
                return True, "ok"
            
            # Timezone aware datetime'ları karşılaştır
            if message_date.tzinfo is None:
                message_date = message_date.replace(tzinfo=timezone.utc)
            if last_online.tzinfo is None:
                last_online = last_online.replace(tzinfo=timezone.utc)
            
            # 1 dakika tolerans
            time_diff = abs((message_date - last_online).total_seconds())
            
            if time_diff <= 60:
                self.stats['skipped'] += 1
                return False, "reaction_time"
            
            return True, "ok"
            
        except Exception:
            return True, "ok"
    
    async def get_active_users(self, group_entity):
        """Tepki veren ve mesaj gönderen kullanıcıları topla - GÜNCELLENDİ"""
        try:
            unique_users = set()
            processed_users = []
            offset_id = 0
            processed_messages = 0
            
            self.log_progress(f"Hedef kullanıcı sayısı: {self.target_user_count}")
            self.log_progress(f"Global Blacklist'te {len(self.blacklist)} kullanıcı var")
            self.log_progress(f"Yönetici atlama: {'Açık' if self.skip_admins else 'Kapalı'}")
            self.log_progress(f"Mesaj gönderenler dahil: {'Evet' if self.include_message_senders else 'Hayır'}")
            
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
                    
                    # 1. Mesaj gönderenleri dahil et (YENİ)
                    if self.include_message_senders and message.sender_id:
                        try:
                            if message.sender_id not in unique_users:
                                sender = await self.client.get_entity(message.sender_id)
                                should_send, reason = await self.should_send_to_user(sender, message.date, group_entity)
                                if should_send:
                                    unique_users.add(sender.id)
                                    processed_users.append(sender)
                                    self.stats['message_senders'] += 1
                                    
                                    if len(unique_users) >= self.target_user_count:
                                        self.log_progress(f"Hedef sayıya ulaşıldı: {len(unique_users)}", "SUCCESS")
                                        return processed_users[:self.target_user_count]
                                    
                        except Exception:
                            pass
                    
                    # 2. Tepki verenleri dahil et (MEVCUT)
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
                                        should_send, reason = await self.should_send_to_user(user, message.date, group_entity)
                                        if should_send:
                                            unique_users.add(user.id)
                                            processed_users.append(user)
                                            self.stats['reaction_users'] += 1
                                            
                                            if len(unique_users) >= self.target_user_count:
                                                self.log_progress(f"Hedef sayıya ulaşıldı: {len(unique_users)}", "SUCCESS")
                                                return processed_users[:self.target_user_count]
                                
                                await asyncio.sleep(self.request_delay)
                                
                            except Exception:
                                continue

                    offset_id = message.id
                
                # Progress update
                if processed_messages % 50 == 0:
                    total_skipped = (self.stats['blacklisted'] + self.stats['admin_skipped'] + 
                                   self.stats['blocked_skipped'] + self.stats['skipped'])
                    self.log_progress(f"İşlenen mesaj: {processed_messages}, Bulunan: {len(unique_users)}, "
                                    f"Atlanan: {total_skipped} (Tepki: {self.stats['reaction_users']}, "
                                    f"Mesaj: {self.stats['message_senders']}, Blacklist: {self.stats['blacklisted']}, "
                                    f"Yönetici: {self.stats['admin_skipped']})")
                
                await asyncio.sleep(1)
            
            self.log_progress(f"Toplam {len(processed_users)} benzersiz kullanıcı bulundu")
            self.log_progress(f"Tepki veren: {self.stats['reaction_users']}, Mesaj gönderen: {self.stats['message_senders']}")
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
            
            # Başarılı gönderimde blacklist'e ekle
            self.add_to_blacklist(user_id)
            self.stats['sent'] += 1
            return True
        except UserBlockedError:
            self.stats['blocked_skipped'] += 1
            return False
        except PeerFloodError:
            self.log_progress("Flood limit! 30 saniye bekleniyor...", "WARNING")
            await asyncio.sleep(30)
            self.stats['failed'] += 1
            return False
        except Exception:
            self.stats['failed'] += 1
            return False
    
    def print_stats(self):
        """İstatistikleri göster"""
        total = (self.stats['sent'] + self.stats['failed'] + self.stats['skipped'] + 
                self.stats['blacklisted'] + self.stats['admin_skipped'] + 
                self.stats['blocked_skipped'])
        
        if total > 0:
            success_rate = (self.stats['sent'] / total) * 100
            print(f"\n📊 Detaylı İstatistikler:")
            print(f"✓ Başarılı gönderim: {self.stats['sent']}")
            print(f"✗ Başarısız gönderim: {self.stats['failed']}")
            print(f"📝 Mesaj gönderenler: {'Dahil' if self.include_message_senders else 'Hariç'}")
            print(f"⏭ Tepki süresi nedeniyle atlanan: {self.stats['skipped']}")
            print(f"🚫 Global Blacklist nedeniyle atlanan: {self.stats['blacklisted']}")
            print(f"👑 Yönetici olduğu için atlanan: {self.stats['admin_skipped']}")
            print(f"🔒 Engelleme nedeniyle atlanan: {self.stats['blocked_skipped']}")
            print(f"📈 Başarı oranı: {success_rate:.1f}%")
            print(f"📊 Toplam işlem: {total}")
    
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
                    
                    await asyncio.sleep(0.5)
                    
                except Exception:
                    continue
            
            # Batch arası dinlenme
            if i + self.batch_size < total_users:
                self.log_progress(f"Batch tamamlandı, 3 saniye bekleniyor...")
                await asyncio.sleep(3)
        
        # Global Blacklist'i kaydet
        self.save_blacklist()
        
        self.log_progress(f"İşlem tamamlandı: {success_count}/{total_users} başarılı", "SUCCESS")
    
    async def cleanup(self):
        """Temizlik işlemleri"""
        if self.client:
            try:
                await self.client.disconnect()
                self.log_progress("Client bağlantısı kapatıldı", "SUCCESS")
            except:
                pass
        
        # Final global blacklist save
        if hasattr(self, 'blacklist_file') and self.blacklist_file:
            self.save_blacklist()
            
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
            users = await self.get_active_users(group_entity)
            if not users:
                self.log_progress("Yeterli kullanıcı bulunamadı!", "WARNING")
                return
            
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
    print("🤖 Telegram Draft Sender - Flexible Group Support")
    print("=" * 50)
    
    if not check_requirements():
        return
    
    print("\n📋 Termux Kurulum:")
    print("1. pkg update && pkg upgrade")
    print("2. pkg install python")
    print("3. pip install telethon")
    
    print("\n📢 Grup Desteği:")
    print("• Herkese açık gruplar: https://t.me/grupadi")
    print("• Gizli/Özel gruplar: Grup ismini yazın")
    print("• Üye olduğunuz gruplar: Tam ismi yazın")
    
    print("\n🚫 Global Blacklist Özellikleri:")
    print("• Gönderilen kullanıcılar merkezi bir dosyada kaydedilir")
    print("• Hangi telefon numarası kullanılırsa kullanılsın aynı liste")
    print("• Bir daha HİÇBİR telefon numarasıyla gönderim yapılmaz")
    print("• Tüm hesaplar için ortak koruma sağlar")
    
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