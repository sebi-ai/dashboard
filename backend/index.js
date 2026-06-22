import express from 'express';
import { google } from 'googleapis';
import dotenv from 'dotenv';
import cors from 'cors';

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

const CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const RedirectURI = process.env.GOOGLE_REDIRECT_URI;

const oauth2Client = new google.auth.OAuth2(
  CLIENT_ID,
  CLIENT_SECRET,
  RedirectURI
);

// 1. OAuth starten
app.get('/auth/google', (req, res) => {
  const authUrl = oauth2Client.generateAuthUrl({
    access_type: 'offline',
    scope: 'https://www.googleapis.com/auth/calendar.readonly',
  });
  res.json({ url: authUrl });
});

// 2. Callback nach Google
app.get('/auth/google/callback', async (req, res) => {
  const { code } = req.query;
  const { tokens } = await oauth2Client.getToken(code);
  oauth2Client.setCredentials(tokens);

  // Tipp: tokens.access_token und tokens.refresh_token speichern in DB
  // hier nur kurz zurückgeben:
  res.json({
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
  });
});

// 3. Kalender-Termine laden
app.get('/calendar/events', async (req, res) => {
  const accessToken = req.query.accessToken; // oder aus DB göre User
  if (!accessToken) {
    return res.status(400).json({ error: 'accessToken required' });
  }

  oauth2Client.setCredentials({ access_token: accessToken });

  const calendar = google.calendar({ version: 'v3', auth: oauth2Client });

  try {
    const result = await calendar.events.list({
      calendarId: 'primary',
      timeMin: new Date().toISOString(),
      maxResults: 10,
      singleEvents: true,
      orderBy: 'startTime',
    });

    res.json(result.data.items);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch events' });
  }
});

app.listen(process.env.PORT || 8000, () => {
  console.log('Backend running on port', process.env.PORT || 8000);
});