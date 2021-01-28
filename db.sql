-- Adminer 4.7.8 MySQL dump

SET NAMES utf8;
SET time_zone = '+00:00';
SET foreign_key_checks = 0;

CREATE DATABASE `ipblocker` /*!40100 DEFAULT CHARACTER SET utf8 */;
USE `ipblocker`;

DROP TABLE IF EXISTS `ban`;
CREATE TABLE `ban` (
  `idBan` int(11) NOT NULL AUTO_INCREMENT,
  `idIP` int(11) NOT NULL,
  `level` int(11) DEFAULT NULL,
  `rule` varchar(255) DEFAULT NULL,
  `timestamp` bigint(20) DEFAULT NULL,
  `banned` tinyint(4) NOT NULL DEFAULT 0,
  PRIMARY KEY (`idBan`),
  KEY `idIP` (`idIP`),
  CONSTRAINT `ban_ibfk_1` FOREIGN KEY (`idIP`) REFERENCES `ip` (`idIP`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;


DROP TABLE IF EXISTS `ip`;
CREATE TABLE `ip` (
  `idIP` int(11) NOT NULL AUTO_INCREMENT,
  `ip` varchar(255) NOT NULL,
  `country` varchar(2) DEFAULT NULL,
  `city` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`idIP`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;


-- 2021-01-27 23:13:45
